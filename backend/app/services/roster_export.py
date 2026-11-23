from dataclasses import dataclass
from datetime import date, time
from io import BytesIO

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


TABLE_HEADERS = ("STATION", "CREW MEMBER", "SCHEDULE")
TABLE_COLUMN_WIDTHS = (140, 250, 185)
HEADER_COLOR = "173F5F"
ALTERNATE_ROW_COLOR = "F2F6F8"


@dataclass(frozen=True)
class ScheduleRosterRow:
    station: str
    shift: str
    start_time: time
    end_time: time
    crew_names: tuple[str, ...]
    coverage: str
    status: str


def _clock_time(value: time) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def _schedule_time(row: ScheduleRosterRow) -> str:
    return f"{_clock_time(row.start_time)} - {_clock_time(row.end_time)}"


def _roster_crew_names(row: ScheduleRosterRow) -> tuple[str, ...]:
    if row.crew_names:
        return row.crew_names
    return () if row.status == "Complete" else ("UNASSIGNED",)


def roster_rows(
    rows: list[ScheduleRosterRow],
) -> list[tuple[str, str, str, time]]:
    entries = [
        (
            row.station,
            crew_name,
            _schedule_time(row),
            row.start_time,
        )
        for row in rows
        for crew_name in _roster_crew_names(row)
    ]
    entries.sort(
        key=lambda entry: (
            entry[0].casefold(),
            entry[3],
            entry[1].casefold(),
        )
    )
    return entries


def _set_cell_shading(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def _set_cell_border(cell, color: str = "D9E2E8") -> None:
    properties = cell._tc.get_or_add_tcPr()
    borders = properties.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        properties.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = qn(f"w:{edge}")
        element = borders.find(tag)
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def _set_cell_text(cell, value: str, *, bold: bool, color: str, size: int) -> None:
    cell.text = value
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for paragraph in cell.paragraphs:
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        for run in paragraph.runs:
            run.bold = bold
            run.font.name = "Aptos"
            run.font.size = Pt(size)
            run.font.color.rgb = RGBColor.from_string(color)


def build_schedule_docx(
    branch_name: str,
    schedule_date: date,
    rows: list[ScheduleRosterRow],
) -> bytes:
    document = Document()
    section = document.sections[0]
    section.page_width = Inches(8.27)
    section.page_height = Inches(11.69)
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.55)
    section.right_margin = Inches(0.55)

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(4)
    title_run = title.add_run("DAILY CREW SCHEDULE")
    title_run.bold = True
    title_run.font.name = "Aptos Display"
    title_run.font.size = Pt(19)
    title_run.font.color.rgb = RGBColor.from_string(HEADER_COLOR)

    details = document.add_paragraph()
    details.alignment = WD_ALIGN_PARAGRAPH.CENTER
    details.paragraph_format.space_after = Pt(14)
    details_run = details.add_run(
        f"{branch_name}  |  {schedule_date.strftime('%B %d, %Y')}  "
        f"({schedule_date.strftime('%A')})"
    )
    details_run.font.name = "Aptos"
    details_run.font.size = Pt(10)
    details_run.font.color.rgb = RGBColor.from_string("52616B")

    table = document.add_table(rows=1, cols=len(TABLE_HEADERS))
    table.autofit = False
    table.style = "Table Grid"
    usable_width_inches = (
        section.page_width - section.left_margin - section.right_margin
    ) / 914400

    def column_width(index: int) -> float:
        return (
            usable_width_inches
            * TABLE_COLUMN_WIDTHS[index]
            / sum(TABLE_COLUMN_WIDTHS)
        )

    for index in range(len(TABLE_HEADERS)):
        table.columns[index].width = Inches(column_width(index))

    for index, (cell, label) in enumerate(zip(table.rows[0].cells, TABLE_HEADERS)):
        cell.width = Inches(column_width(index))
        _set_cell_shading(cell, HEADER_COLOR)
        _set_cell_text(cell, label, bold=True, color="FFFFFF", size=9)

    entries = roster_rows(rows)
    for row_index, (station, crew, schedule, _) in enumerate(entries):
        cells = table.add_row().cells
        for column_index, cell in enumerate(cells):
            cell.width = Inches(column_width(column_index))
        for cell, value in zip(cells[1:], (crew, schedule)):
            if row_index % 2:
                _set_cell_shading(cell, ALTERNATE_ROW_COLOR)
            _set_cell_border(cell)
            _set_cell_text(cell, value, bold=False, color="253746", size=9)

    start_index = 0
    while start_index < len(entries):
        station = entries[start_index][0]
        end_index = start_index + 1
        while end_index < len(entries) and entries[end_index][0] == station:
            end_index += 1
        station_cell = table.cell(start_index + 1, 0)
        if end_index - start_index > 1:
            station_cell = station_cell.merge(table.cell(end_index, 0))
        if start_index % 2:
            _set_cell_shading(station_cell, ALTERNATE_ROW_COLOR)
        _set_cell_border(station_cell)
        _set_cell_text(
            station_cell,
            station,
            bold=True,
            color=HEADER_COLOR,
            size=9,
        )
        station_cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        start_index = end_index

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _safe_pdf_text(value: str) -> str:
    return value.encode("cp1252", errors="replace").decode("cp1252")


def _fit_text(value: str, width: float, font_size: float) -> str:
    value = _safe_pdf_text(value)
    if stringWidth(value, "Helvetica", font_size) <= width:
        return value
    suffix = "..."
    while value and stringWidth(value + suffix, "Helvetica", font_size) > width:
        value = value[:-1]
    return value.rstrip() + suffix


def build_schedule_pdf(
    branch_name: str,
    schedule_date: date,
    rows: list[ScheduleRosterRow],
) -> bytes:
    output = BytesIO()
    page_width, page_height = A4
    margin = 18 * mm
    table_width = page_width - 2 * margin
    column_widths = [
        table_width * width / sum(TABLE_COLUMN_WIDTHS)
        for width in TABLE_COLUMN_WIDTHS
    ]
    x_positions = [margin]
    for width in column_widths:
        x_positions.append(x_positions[-1] + width)

    page = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    page.setTitle(f"Crew Schedule - {branch_name} - {schedule_date.isoformat()}")
    page.setAuthor("SmartShift")

    def draw_header() -> float:
        page.setFillColor(colors.HexColor(f"#{HEADER_COLOR}"))
        page.setFont("Helvetica-Bold", 17)
        page.drawCentredString(
            page_width / 2,
            page_height - 25 * mm,
            "DAILY CREW SCHEDULE",
        )
        page.setFillColor(colors.HexColor("#52616B"))
        page.setFont("Helvetica", 9)
        page.drawCentredString(
            page_width / 2,
            page_height - 33 * mm,
            _safe_pdf_text(
                f"{branch_name}  |  {schedule_date.strftime('%B %d, %Y')}  "
                f"({schedule_date.strftime('%A')})"
            ),
        )
        return page_height - 43 * mm

    def draw_table_header(y: float) -> float:
        header_height = 22
        page.setFillColor(colors.HexColor(f"#{HEADER_COLOR}"))
        page.roundRect(
            margin,
            y - header_height,
            table_width,
            header_height,
            4,
            fill=1,
            stroke=0,
        )
        page.setFillColor(colors.white)
        page.setFont("Helvetica-Bold", 8)
        for index, label in enumerate(TABLE_HEADERS):
            x = x_positions[index]
            page.drawString(x + 8, y - 14, label)
        return y - header_height

    y = draw_table_header(draw_header())
    page_table_top = y
    entries = roster_rows(rows)
    station_groups: list[tuple[str, list[tuple[str, str, time]]]] = []
    for station, crew, schedule, start_time in entries:
        if not station_groups or station_groups[-1][0] != station:
            station_groups.append((station, []))
        station_groups[-1][1].append((crew, schedule, start_time))

    row_height = 23
    row_index = 0
    for station, station_entries in station_groups:
        entry_index = 0
        while entry_index < len(station_entries):
            available_rows = int((y - margin) // row_height)
            if available_rows == 0:
                page.showPage()
                y = draw_table_header(draw_header())
                page_table_top = y
                available_rows = int((y - margin) // row_height)

            remaining_rows = len(station_entries) - entry_index
            if (
                remaining_rows <= int((page_table_top - margin) // row_height)
                and remaining_rows > available_rows
                and y != page_table_top
            ):
                page.showPage()
                y = draw_table_header(draw_header())
                page_table_top = y
                available_rows = int((y - margin) // row_height)

            fragment_count = min(remaining_rows, available_rows)
            group_top = y
            for crew, schedule, _ in station_entries[
                entry_index:entry_index + fragment_count
            ]:
                row_bottom = y - row_height
                if row_index % 2:
                    page.setFillColor(colors.HexColor(f"#{ALTERNATE_ROW_COLOR}"))
                    page.rect(
                        x_positions[1],
                        row_bottom,
                        table_width - column_widths[0],
                        row_height,
                        fill=1,
                        stroke=0,
                    )
                page.setStrokeColor(colors.HexColor("#D9E2E8"))
                page.setLineWidth(0.45)
                page.line(x_positions[1], row_bottom, margin + table_width, row_bottom)

                page.setFillColor(colors.HexColor(f"#{HEADER_COLOR}"))
                page.setFont("Helvetica-Bold", 9)
                page.drawString(
                    x_positions[1] + 8,
                    row_bottom + 7.5,
                    _fit_text(crew, column_widths[1] - 16, 9),
                )
                page.setFillColor(colors.HexColor("#253746"))
                page.setFont("Helvetica", 9)
                page.drawString(
                    x_positions[2] + 8,
                    row_bottom + 7.5,
                    _fit_text(schedule, column_widths[2] - 16, 9),
                )
                y = row_bottom
                row_index += 1

            entry_index += fragment_count
            page.setStrokeColor(colors.HexColor("#D9E2E8"))
            page.line(x_positions[1], group_top, x_positions[1], y)
            page.line(margin, y, margin + table_width, y)
            page.setFillColor(colors.HexColor(f"#{HEADER_COLOR}"))
            page.setFont("Helvetica-Bold", 9)
            page.drawCentredString(
                x_positions[0] + column_widths[0] / 2,
                (group_top + y) / 2 - 3,
                _fit_text(station, column_widths[0] - 16, 9),
            )
            if entry_index < len(station_entries):
                page.showPage()
                y = draw_table_header(draw_header())
                page_table_top = y

    page.save()
    return output.getvalue()
