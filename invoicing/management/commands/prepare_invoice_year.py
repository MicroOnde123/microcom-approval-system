from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _, override

from invoicing.year_preparation import prepare_invoice_year


class Command(BaseCommand):
    help = "Prepare next year's unverified invoice sequences from verified current-year series."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--language", choices=["en", "fr"], default="en")

    def handle(self, *args, **options):
        with override(options["language"]):
            try:
                report = prepare_invoice_year()
            except (ObjectDoesNotExist, ValidationError):
                raise CommandError(_("Preparation failed. Review company and sequence configuration.")) from None
            for key, label in [("prepared", _("Prepared")), ("existing", _("Already existing")),
                               ("unverified", _("Unverified: administrator attestation required"))]:
                self.stdout.write("%s %s: %s" % (report["year"], label, ", ".join(report[key]) or "—"))
            if report["conflicts"]:
                for left, right in report["conflicts"]:
                    self.stderr.write(_("Potential numbering conflict: %(left)s / %(right)s") % {"left": left, "right": right})
                raise CommandError(_("No sequences prepared. Resolve conflicting formats first."))
            if not report["sources"]:
                self.stdout.write(_("No verified current-year invoice series found."))
