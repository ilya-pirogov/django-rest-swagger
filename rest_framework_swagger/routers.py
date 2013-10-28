from django.contrib.admindocs.views import simplify_regex
from rest_framework.routers import SimpleRouter, Route, url
from rest_framework.views import APIView

from rest_framework_swagger.apidocview import APIDocView

__registred_api = []


def _append_api(pattern, methods):

    callback = _get_pattern_api_callback(pattern)

    path = simplify_regex('/' + pattern.regex.pattern)
    path = path.replace('<', '{').replace('>', '}')

    __registred_api.append({
        'path': path,
        'pattern': pattern,
        'callback': callback,
        'methods': methods
    })


def _get_pattern_api_callback(pattern):
    """
    Verifies that pattern callback is a subclass of APIView, and returns the class
    Handles older django & django rest 'cls_instance'
    """
    if not hasattr(pattern, 'callback'):
        return

    if (hasattr(pattern.callback, 'cls') and
            issubclass(pattern.callback.cls, APIView) and
            not issubclass(pattern.callback.cls, APIDocView)):

        return pattern.callback.cls

    elif (hasattr(pattern.callback, 'cls_instance') and
            isinstance(pattern.callback.cls_instance, APIView) and
            not issubclass(pattern.callback.cls_instance, APIDocView)):

        return pattern.callback.cls_instance


def get_apis(filter_path=None):
    """
    Returns all the DRF APIViews found in the project URLs

    patterns -- supply list of patterns (optional)
    """
    if filter_path is None:
        return __registred_api

    return [api for api in __registred_api
            if api['path'].startswith('/' + filter_path)]


def get_top_level_apis():
    """
    Returns the 'top level' APIs (ie. swagger 'resources')

    apis -- list of APIs as returned by self.get_apis
    """
    root_paths = set()

    api_paths = [endpoint['path'].strip("/") for endpoint in __registred_api]

    for path in api_paths:
        if '{' in path:
            continue
        root_paths.add(path)

    return root_paths


class SwaggerRouter(SimpleRouter):
    def register(self, prefix, viewset, base_name=None, extra_params=None):
        if base_name is None:
            base_name = self.get_default_base_name(viewset)
        if extra_params is None:
            extra_params = {}
        self.registry.append((prefix, viewset, base_name, extra_params))

    def get_urls(self):
        """
        Use the registered viewsets to generate a list of URL patterns.
        """
        ret = []

        for prefix, viewset, basename, params in self.registry:
            lookup = self.get_lookup_regex(viewset)
            routes = self.get_routes(viewset)

            for route in routes:

                # Only actions which actually exist on the viewset will be bound
                mapping = self.get_method_map(viewset, route.mapping)
                if not mapping:
                    continue

                # Build the url pattern
                params['prefix'] = prefix
                params['lookup'] = lookup
                params['trailing_slash'] = self.trailing_slash
                regex = route.url.format(**params)

                view = viewset.as_view(mapping, **route.initkwargs)
                name = route.name.format(basename=basename)

                pattern = url(regex, view, name=name)
                ret.append(pattern)
                _append_api(pattern, mapping)

        return ret