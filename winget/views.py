from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Package
from .util import load_tenant, return_jsonresponse, parse_jsonrequest

@require_GET
@load_tenant
def index(*_):
    # The sole motivation for this view is that we want to be able to
    # reverse('winget:index') in instructions for setting up the winget source.
    return HttpResponse("Please log in at /admin for instructions.")

@require_GET
@load_tenant
@return_jsonresponse
def information(*_):
    return {
        'SourceIdentifier': 'api.winget.pro',
        'ServerSupportedVersions': ['1.1.0']
    }

@require_POST
@csrf_exempt
@load_tenant
@parse_jsonrequest
@return_jsonresponse
def manifestSearch(_, data, tenant):
    db_query = Q(tenant=tenant)
    if 'Query' in data:
        keyword = data['Query']['KeyWord']
        db_query &= Q(name__icontains=keyword)
    inclusions_query = Q()
    for inclusion in data.get('Inclusions', []):
        field = inclusion['PackageMatchField']
        if field == 'PackageName':
            keyword = inclusion['RequestMatch']['KeyWord']
            inclusions_query |= Q(name__icontains=keyword)
        elif field == 'ProductCode':
            keyword = inclusion['RequestMatch']['KeyWord']
            # We don't have a ProductCode. Use the identifier instead.
            inclusions_query |= Q(identifier__icontains=keyword)
        elif field == 'PackageFamilyName':
            keyword = inclusion['RequestMatch']['KeyWord']
            # We don't have family name. Use the name instead.
            inclusions_query |= Q(name__icontains=keyword)
    db_query &= inclusions_query
    for filter_ in data.get('Filters', []):
        field = filter_['PackageMatchField']
        keyword = filter_['RequestMatch']['KeyWord']
        if field == 'PackageIdentifier':
            db_query &= Q(identifier__icontains=keyword)
    return [
        {
            'PackageIdentifier': package.identifier,
            'PackageName': package.name,
            'Publisher': package.publisher,
            'Versions': [
                {'PackageVersion': version.version}
                for version in package.version_set.all()
            ]
        }
        for package in Package.objects.filter(db_query)
        if package.version_set.exists()
    ]

@require_GET
@load_tenant
def packageManifests(request, tenant, identifier):
    try:
        package = Package.objects.get(tenant=tenant, identifier=identifier)
    except ObjectDoesNotExist:
        # This is a peculiarity / inconsistency of the winget client. The API
        # design docs say that packageManifests should return 404 when a package
        # does not exist. But winget doesn't gracefully handle this case.
        # Instead, it expects HTTP 204.
        # See: https://github.com/microsoft/winget-cli-restsource/issues/170
        return HttpResponse(status=204)
    return _packageManifests(request, package)

@return_jsonresponse
def _packageManifests(request, package):
    return {
        'PackageIdentifier': package.identifier,
        'Versions': [
            {
                'PackageVersion': version.version,
                'DefaultLocale': {
                    'PackageLocale': 'en-us',
                    'Publisher': package.publisher,
                    'PackageName': package.name,
                    'ShortDescription': package.description
                },
                'Installers': [
                    {
                        'Architecture': installer.architecture,
                        'InstallerType': installer.type,
                        'InstallerUrl':
                            request.build_absolute_uri(installer.file.url),
                        'InstallerSha256': installer.sha256,
                        'Scope': scope
                    }
                    for installer in version.installer_set.all()
                    for scope in installer.scopes
                ]
            }
            for version in package.version_set.all()
        ]
    }