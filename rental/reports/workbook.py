from datetime import date, datetime
from decimal import Decimal
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

INK = "0F172A"
ACCENT = "1B3A5C"
MUTED = "64748B"
BAND = "F1F5F9"
LINE = "E2E8F0"

TITLE_FONT = Font(name="Calibri", size=16, bold=True, color=INK)
SUBTITLE_FONT = Font(name="Calibri", size=10, color=MUTED)
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
TOTAL_FONT = Font(name="Calibri", size=11, bold=True, color=INK)

HEADER_FILL = PatternFill("solid", fgColor=ACCENT)
TOTAL_FILL = PatternFill("solid", fgColor=BAND)

THIN = Side(style="thin", color=LINE)
CELL_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def currency_format():
    symbol = settings.DEFAULT_CURRENCY_SYMBOL
    return f'"{symbol}"#,##0.00'


DATE_FORMAT = "dd/mm/yyyy"
DATETIME_FORMAT = "dd/mm/yyyy hh:mm"
NUMBER_FORMAT = "#,##0"
PERCENT_FORMAT = "0.0%"


class Column:
    
    def __init__(self, header, accessor, width=18, kind="text", total=False):
        self.header = header
        self.accessor = accessor
        self.width = width
        self.kind = kind  
        self.total = total

    def value(self, obj):
        if callable(self.accessor):
            return self.accessor(obj)

        value = obj
        for part in self.accessor.split("__"):
            value = getattr(value, part, None)
            if value is None:
                return None
        return value

    @property
    def number_format(self):
        return {
            "money": currency_format(),
            "number": NUMBER_FORMAT,
            "date": DATE_FORMAT,
            "datetime": DATETIME_FORMAT,
            "percent": PERCENT_FORMAT,
        }.get(self.kind)


class ReportWorkbook:

    def __init__(self, title, subtitle=""):
        self.title = title
        self.subtitle = subtitle
        self.wb = Workbook()
        self._first_sheet = True

    def _new_sheet(self, name):
        # Headings arrive as lazy translation proxies; openpyxl only writes
        # real strings, so every caption is resolved here.
        safe = str(name)[:31].replace("/", "-").replace("\\", "-")
        if self._first_sheet:
            sheet = self.wb.active
            sheet.title = safe
            self._first_sheet = False
            return sheet
        return self.wb.create_sheet(safe)

    def add_sheet(self, name, columns, rows, description="", table_name=None):
        """Write a titled, filtered, formatted table."""
        sheet = self._new_sheet(name)
        rows = list(rows)

        sheet["A1"] = str(self.title)
        sheet["A1"].font = TITLE_FONT
        sheet["A2"] = str(description or self.subtitle)
        sheet["A2"].font = SUBTITLE_FONT
        sheet["A3"] = _("Generated %(when)s · %(count)s record(s)") % {
            "when": timezone.localtime().strftime("%d %B %Y, %H:%M"),
            "count": len(rows),
        }
        sheet["A3"].font = SUBTITLE_FONT

        header_row = 5

        # -- headers --------------------------------------------------------
        for index, column in enumerate(columns, start=1):
            cell = sheet.cell(row=header_row, column=index, value=str(column.header))
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(vertical="center", horizontal="left")
            cell.border = CELL_BORDER
            sheet.column_dimensions[get_column_letter(index)].width = column.width

        sheet.row_dimensions[header_row].height = 22

        # -- body -----------------------------------------------------------
        for offset, obj in enumerate(rows, start=1):
            for index, column in enumerate(columns, start=1):
                value = column.value(obj)

                if isinstance(value, Decimal):
                    value = float(value)
                elif isinstance(value, datetime):
                    value = timezone.localtime(value).replace(tzinfo=None)
                elif value is not None and not isinstance(
                    value, (int, float, date, str)
                ):
                    value = str(value)

                cell = sheet.cell(row=header_row + offset, column=index, value=value)
                cell.border = CELL_BORDER
                if column.number_format:
                    cell.number_format = column.number_format
                if column.kind in {"money", "number", "percent"}:
                    cell.alignment = Alignment(horizontal="right")

        last_row = header_row + len(rows)

        # -- totals ---------------------------------------------------------
        if rows and any(c.total for c in columns):
            total_row = last_row + 1
            for index, column in enumerate(columns, start=1):
                cell = sheet.cell(row=total_row, column=index)
                cell.fill = TOTAL_FILL
                cell.font = TOTAL_FONT
                cell.border = CELL_BORDER
                if index == 1:
                    cell.value = _("Total")
                elif column.total:
                    start = get_column_letter(index) + str(header_row + 1)
                    end = get_column_letter(index) + str(last_row)
                    cell.value = f"=SUM({start}:{end})"
                    if column.number_format:
                        cell.number_format = column.number_format
                    cell.alignment = Alignment(horizontal="right")

        if rows:
            ref = f"A{header_row}:{get_column_letter(len(columns))}{last_row}"
            table = Table(
                displayName=(table_name or name).replace(" ", "_").replace("-", "_")[:30],
                ref=ref,
            )
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleLight9", showRowStripes=True
            )
            try:
                sheet.add_table(table)
            except ValueError:
                sheet.auto_filter.ref = ref
        else:
            sheet.cell(
                row=header_row + 1,
                column=1,
                value=_("No records match these filters."),
            ).font = SUBTITLE_FONT

        sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
        return sheet

    def add_summary_sheet(self, name, pairs, description=""):
        sheet = self._new_sheet(name)

        sheet["A1"] = str(self.title)
        sheet["A1"].font = TITLE_FONT
        sheet["A2"] = str(description or self.subtitle)
        sheet["A2"].font = SUBTITLE_FONT

        sheet.column_dimensions["A"].width = 34
        sheet.column_dimensions["B"].width = 22

        row = 4
        for label, value, kind in pairs:
            label_cell = sheet.cell(row=row, column=1, value=str(label))
            label_cell.font = Font(bold=True, color=INK)
            label_cell.border = CELL_BORDER

            if isinstance(value, Decimal):
                value = float(value)
            value_cell = sheet.cell(row=row, column=2, value=value)
            value_cell.border = CELL_BORDER
            value_cell.alignment = Alignment(horizontal="right")
            if kind == "money":
                value_cell.number_format = currency_format()
            elif kind == "number":
                value_cell.number_format = NUMBER_FORMAT
            row += 1

        return sheet

    def response(self, filename):
        response = HttpResponse(
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        )
        stamp = timezone.localdate().strftime("%Y-%m-%d")
        safe = "".join(
            c for c in filename if c.isalnum() or c in "-_ "
        ).strip().replace(" ", "-")
        response["Content-Disposition"] = (
            f'attachment; filename="{safe}-{stamp}.xlsx"'
        )
        self.wb.save(response)
        return response
