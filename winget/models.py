from django.core.validators import MinLengthValidator, RegexValidator
from django.db.models import Model, CharField, DateTimeField, ForeignKey, \
    CASCADE, TextField, FileField
from django.db.models.signals import pre_save
from django.dispatch import receiver
from hashlib import sha256
from tenants.models import Tenant
from winget.util import CharFieldFromChoices, randomize_filename


class Package(Model):
    tenant = ForeignKey(Tenant, on_delete=CASCADE)
    identifier = CharField(
        max_length=128,
        help_text='Unique identifier for the package (e.g. WinMerge.WinMerge).'
    )
    name = CharField(
        max_length=256, validators=[MinLengthValidator(2)],
        help_text='Package name (e.g. WinMerge).'
    )
    publisher = CharField(
        max_length=256, validators=[MinLengthValidator(2)],
        help_text='Package publisher (eg. Thingamahoochie Software)'
    )
    description = TextField(
        max_length=256, validators=[MinLengthValidator(3)],
        help_text=
            'Package description (e.g. "An open source differencing tool.")'
    )
    created = DateTimeField(auto_now_add=True)
    modified = DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'identifier')

    def __str__(self):
        return self.name


class Version(Model):
    package = ForeignKey(Package, on_delete=CASCADE)
    version = CharField(
        max_length=128, blank=True,
        help_text="The package's version (eg. 2.16.26 or 1.2.3.4)."
    )
    created = DateTimeField(auto_now_add=True)
    modified = DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('package', 'version')

    def __str__(self):
        result = self.package.name
        if self.version:
            result += ' ' + self.version
        return result


def installer_upload_to(instance, filename):
    # Randomize the upload path. This prevents users from guessing it and
    # prevents clashes.
    randomized_filename = randomize_filename(filename)
    return f'{instance.version.package.tenant.uuid}/{randomized_filename}'


class Installer(Model):
    version = ForeignKey(Version, on_delete=CASCADE)
    architecture = CharFieldFromChoices('x86', 'x64', 'arm', 'arm64')
    type = CharFieldFromChoices(
        'msix', 'msi', 'appx', 'exe', 'zip', 'inno', 'nullsoft', 'wix', 'burn',
        'pwa', 'msstore'
    )
    scope = CharFieldFromChoices(
        'user', 'machine', 'both', default='both',
        help_text=
        "Is this a machine-wide installer, just for the current user, or both?"
    )
    file = FileField(upload_to=installer_upload_to)
    sha256 = CharField(
        max_length=64, validators=[RegexValidator('^[a-fA-F0-9]{64}$')]
    )
    created = DateTimeField(auto_now_add=True)
    modified = DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('version', 'architecture', 'type')

    @property
    def scopes(self):
        return ['user', 'machine'] if self.scope == 'both' else [self.scope]

    def __str__(self):
        return self.file.url


@receiver(pre_save, sender=Installer)
def pre_installer_save(sender, instance, **kwargs):
    m = sha256()
    instance.file.seek(0)
    for chunk in instance.file.chunks():
        m.update(chunk)
    instance.sha256 = m.digest().hex()