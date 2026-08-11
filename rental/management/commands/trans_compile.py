from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from rental.i18n_tools import check_placeholders, parse_po, write_mo
class Command(BaseCommand):
    help = "Compile .po catalogues to .mo (no gettext needed)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--locale", "-l", action="append", dest="locales",
            help="Only process these locales (repeatable).",
        )
        parser.add_argument(
            "--strict", action="store_true",
            help="Exit non-zero if any locale is not fully translated.",
        )

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        locale_dir = Path(settings.LOCALE_PATHS[0])

        languages = [code for code, _name in settings.LANGUAGES]
        if options.get("locales"):
            languages = [c for c in languages if c in options["locales"]]

        incomplete = []
        broken = []

        for language in languages:
            po_path = locale_dir / language / "LC_MESSAGES" / "django.po"
            mo_path = po_path.with_suffix(".mo")

            if not po_path.exists():
                self.stdout.write(self.style.WARNING(f"  {language}: no .po file"))
                continue

            catalogue = parse_po(po_path)
            total = len(catalogue.messages)
            done = catalogue.translated_count

            problems = check_placeholders(catalogue)
            if problems:
                broken.append((language, problems))
                self.stdout.write(
                    self.style.ERROR(
                        f"  {language}: {len(problems)} message(s) with mismatched "
                        f"placeholders — not compiled"
                    )
                )
                continue

            written = write_mo(mo_path, catalogue)

            percent = (done / total * 100) if total else 100.0
            style = self.style.SUCCESS if done == total else self.style.WARNING
            self.stdout.write(
                style(
                    f"  {language}: {done}/{total} translated ({percent:.0f}%), "
                    f"{written} entries -> {mo_path.relative_to(base_dir)}"
                )
            )

            if done < total:
                incomplete.append((language, total - done))

        if broken:
            self.stdout.write("")
            for language, problems in broken:
                for source, target, missing, extra in problems:
                    self.stdout.write(self.style.ERROR(f"  {language}: {source!r}"))
                    self.stdout.write(f"      translated as {target!r}")
                    if missing:
                        self.stdout.write(f"      never substituted: {sorted(missing)}")
                    if extra:
                        self.stdout.write(f"      unknown placeholders: {sorted(extra)}")
            raise CommandError(
                "Fix the placeholders above — they would raise at render time."
            )

        if incomplete:
            self.stdout.write("")
            for language, missing in incomplete:
                self.stdout.write(f"  {language}: {missing} string(s) still untranslated")
            if options.get("strict"):
                raise CommandError("Some locales are incomplete (--strict).")
        else:
            self.stdout.write(self.style.SUCCESS("\nAll locales fully translated."))
