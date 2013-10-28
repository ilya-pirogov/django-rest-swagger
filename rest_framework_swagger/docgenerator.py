"""
Generates Documentation
"""
import re
from django.contrib.admindocs.utils import trim_docstring
from rest_framework import viewsets
from rest_framework.views import get_view_name, get_view_description


class DocumentationGenerator(object):

    def generate(self, apis):
        """
        Returns documentaion for a list of APIs
        """
        api_docs = []
        for api in apis:
            api_docs.append({
                'description': self.__get_description__(api['callback']),
                'path': api['path'],
                'operations': self.__get_operations__(api),
            })

        return api_docs

    def __get_operations__(self, api):
        """
        Returns docs for the allowed methods of an API endpoint
        """
        operations = []
        callback = api['callback']

        for http_method, view_method in api['methods'].items():
            http_method = http_method.upper()

            operation = {
                'httpMethod': http_method,
                'summary': self.__get_method_docs__(
                    callback, http_method, view_method),
                'nickname': self.__get_nickname__(callback),
                'notes': self.__get_notes__(callback, view_method),
                'responseClass': self.__get_serializer_class_name__(callback),
            }

            parameters = self.get_parameters(api, http_method, view_method)
            if len(parameters) > 0:
                operation['parameters'] = parameters

            operations.append(operation)

        return operations

    def __get_name__(self, callback):
        """
        Returns the APIView class name
        """
        return get_view_name(callback)

    def __get_description__(self, callback):
        """
        Returns the first sentence of the first line of the class docstring
        """
        return get_view_description(callback).split("\n")[0].split(".")[0]

    def __eval_method_docstring_(self, callback, method):
        """
        Attempts to fetch the docs for a class method. Returns None
        if the method does not exist
        """
        try:
            return eval("callback.%s.__doc__" % (str(method).lower()))
        except AttributeError:
            return None

    def __get_method_docs__(self, callback, http_method, view_method):
        """
        Attempts to retrieve method specific docs for an
        endpoint. If none are available, the class docstring
        will be used
        """
        for name, desc in self.__parse_from_docstring__(callback, view_method):
            if name == http_method:
                return desc

        docs = self.__eval_method_docstring_(callback, view_method)

        if docs is None:
            docs = self.__get_description__(callback)
        docs = trim_docstring(docs).split('\n')[0]

        return docs

    def __get_nickname__(self, callback):
        """ Returns the APIView's nickname """
        return self.__get_name__(callback).replace(' ', '_')

    def __get_notes__(self, callback, method=None):
        """
        Returns the body of the docstring trimmed before any parameters are
        listed. First, get the class docstring and then get the method's. The
        methods will always inherit the class comments.
        """
        docstring = ""

        if method is not None:
            class_docs = self.__get_notes__(callback)
            method_docs = self.__eval_method_docstring_(callback, method)

            if class_docs is not None:
                docstring += class_docs
            if method_docs is not None:
                docstring += method_docs
        else:
            docstring = trim_docstring(get_view_description(callback))

        docstring = self.__strip_params_from_docstring__(docstring)
        docstring = docstring.replace("\n", "<br/>")

        return docstring

    def __strip_params_from_docstring__(self, docstring):
        """
        Strips the params from the docstring (ie. myparam -- Some param) will
        not be removed from the text body
        """
        split_lines = trim_docstring(docstring).split('\n')

        cut_off = None
        for index, line in enumerate(split_lines):
            line = line.strip()
            if line.find('--') != -1:
                cut_off = index
                break
        if cut_off is not None:
            split_lines = split_lines[0:cut_off]

        return "<br/>".join(split_lines)

    def get_models(self, apis):
        """
        Builds a list of Swagger 'models'. These represent
        DRF serializers and their fields
        """
        serializers = self.__get_serializer_set__(apis)

        models = {}

        for serializer in serializers:
            properties = self.__get_serializer_fields__(serializer)

            models[serializer.__name__] = {
                'id': serializer.__name__,
                'properties': properties,
            }

        return models

    def get_parameters(self, api, http_method, view_method):
        """
        Returns parameters for an API. Parameters are a combination of HTTP
        query parameters as well as HTTP body parameters that are defined by
        the DRF serializer fields
        """
        params = []
        path_params = self.__build_path_parameters__(api['path'])
        body_params = self.__build_body_parameters__(api['callback'])
        form_params = self.__build_form_parameters__(
            api['callback'], view_method, http_method == 'PATCH')
        query_params = self.__build_query_params__(
            self.__parse_from_docstring__(api['callback'], view_method))

        if path_params:
            params += path_params

        if http_method not in ["GET", "DELETE"]:
            params += form_params

            if not form_params and body_params is not None:
                params.append(body_params)

        if query_params:
            params += query_params

        return params

    def __build_body_parameters__(self, callback):
        serializer_name = self.__get_serializer_class_name__(callback)

        if serializer_name is None:
            return

        return {
            'name': serializer_name,
            'dataType': serializer_name,
            'paramType': 'body',
        }

    def __build_path_parameters__(self, path):
        """
        Gets the parameters from the URL
        """
        url_params = re.findall('/{([^}]*)}', path)
        params = []

        for param in url_params:
            params.append({
                'name': param,
                'dataType': 'string',
                'paramType': 'path',
                'required': True
            })

        return params

    def __build_form_parameters__(self, callback, method, force_optional):
        """
        Builds form parameters from the serializer class
        """
        data = []
        serializer = self.__get_serializer_class__(callback)

        if serializer is None:
            return data

        fields = serializer().get_fields()

        for name, field in fields.items():

            if getattr(field, 'read_only', False):
                continue

            data_type = field.type_label
            max_length = getattr(field, 'max_length', None)
            min_length = getattr(field, 'min_length', None)
            allowable_values = None

            if max_length is not None or min_length is not None:
                allowable_values = {
                    'max': max_length,
                    'min': min_length,
                    'valueType': 'RANGE'
                }

            required = False if force_optional else \
                getattr(field, 'required', None)

            data.append({
                'paramType': 'form',
                'name': name,
                'dataType': data_type,
                'allowableValues': allowable_values,
                'description': getattr(field, 'help_text', ''),
                'defaultValue': getattr(field, 'default', None),
                'required': required
            })

        return data

    def __parse_from_docstring__(self, callback, method=None):
        # Combine class & method level comments. If parameters are specified
        docstring = get_view_description(callback)
        if method is not None:
            method_docs = self.__eval_method_docstring_(callback, method)
            if method_docs:
                docstring += method_docs

        split_lines = docstring.split('\n')

        for line in split_lines:
            param = line.split(' -- ')
            if len(param) == 2:
                yield param[0].strip(), param[1].strip()

    @staticmethod
    def __build_query_params__(params):
        ret = []

        for name, description in params:
            if not name in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'):
                ret.append({
                    'paramType': 'query',
                    'name': name,
                    'description': description,
                    'dataType': '',
                })

        return ret

    def __get_serializer_fields__(self, serializer):
        """
        Returns serializer fields in the Swagger MODEL format
        """
        if serializer is None:
            return

        fields = serializer().get_fields()

        data = {}
        for name, field in fields.items():

            data[name] = {
                'type': field.type_label,
                'required': getattr(field, 'required', None),
                'allowableValues': {
                    'min': getattr(field, 'min_length', None),
                    'max': getattr(field, 'max_length', None),
                    'defaultValue': getattr(field, 'default', None),
                    'readOnly': getattr(field, 'read_only', None),
                    'valueType': 'RANGE',
                }
            }

        return data

    def __get_serializer_class__(self, callback):
        if hasattr(callback, 'get_serializer_class'):
            return callback().get_serializer_class()

    def __get_serializer_class_name__(self, callback):
        serializer = self.__get_serializer_class__(callback)

        if serializer is None:
            return None

        return serializer.__name__

    def __get_serializer_set__(self, apis):
        """
        Returns a set of serializer classes for a provided list
        of APIs
        """
        serializers = set()

        for api in apis:
            serializer = self.__get_serializer_class__(api['callback'])
            if serializer is not None:
                serializers.add(serializer)

        return serializers

