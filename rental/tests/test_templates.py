"""Static checks on the template sources.

Django renders a broken template quietly — the markup just comes out wrong —
so the cheapest place to catch a whole class of authoring mistakes is here,
before anything is rendered at all.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

TEMPLATE_ROOT = Path(settings.BASE_DIR) / "templates"
TEMPLATES = sorted(TEMPLATE_ROOT.rglob("*.html"))


class TemplateSourceTests(TestCase):
    def test_there_are_templates_to_check(self):
        self.assertTrue(TEMPLATES)

    def test_comments_never_span_more_than_one_line(self):
        """`{# … #}` is a single-line form.

        Django's lexer matches it without DOTALL, so a comment broken across
        two lines is not a comment: the opening `{#` and everything after it
        is printed to the page as text.
        """
        offenders = []

        for path in TEMPLATES:
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if line.count("{#") != line.count("#}"):
                    offenders.append(
                        f"{path.relative_to(TEMPLATE_ROOT).as_posix()}:{number}"
                    )

        self.assertEqual(
            offenders,
            [],
            "Use {% comment %}…{% endcomment %} for comments spanning lines; "
            f"unbalanced {{# #}} at: {', '.join(offenders)}",
        )

    def test_block_tags_are_closed(self):
        """A stray {% block %} without its {% endblock %} breaks inheritance."""
        offenders = []

        for path in TEMPLATES:
            source = path.read_text(encoding="utf-8")
            for tag in ("block", "if", "for", "comment", "with"):
                # Word-boundary matching: `{% comment %}` and `{% comment "x" %}`
                # each count once, and `{% endblock content %}` still closes.
                opened = len(re.findall(r"\{%\s*" + tag + r"\b", source))
                closed = len(re.findall(r"\{%\s*end" + tag + r"\b", source))
                if opened != closed:
                    offenders.append(
                        f"{path.relative_to(TEMPLATE_ROOT).as_posix()}: "
                        f"{opened} {{% {tag} %}} vs {closed} {{% end{tag} %}}"
                    )

        self.assertEqual(offenders, [], "; ".join(offenders))
