from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

PACKAGE_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<bookViews><workbookView/></bookViews>
<sheets><sheet name="Schedule" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""

WORKBOOK_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="6">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="16"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><color rgb="FF176F50"/><name val="Calibri"/></font>
<font><b/><color rgb="FFA52834"/><name val="Calibri"/></font>
<font><b/><name val="Calibri"/></font>
</fonts>
<fills count="6">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF087C72"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEAF6F2"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE8F6F1"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF0EF"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFDDE8E5"/></left><right style="thin"><color rgb="FFDDE8E5"/></right><top style="thin"><color rgb="FFDDE8E5"/></top><bottom style="thin"><color rgb="FFDDE8E5"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="8">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="2" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"/>
<xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0"/>
<xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0"/>
<xf numFmtId="0" fontId="5" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _inline_string_cell(reference: str, value: str, style: int = 0) -> str:
    preserved = ' xml:space="preserve"' if value != value.strip() else ""
    return (
        f'<c r="{reference}" s="{style}" t="inlineStr"><is><t{preserved}>'
        f"{escape(value)}</t></is></c>"
    )


def build_schedule_workbook(
    branch_name: str,
    schedule_date: str,
    rows: list[dict[str, str]],
) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        workbook.writestr("_rels/.rels", PACKAGE_RELS_XML)
        workbook.writestr("xl/workbook.xml", WORKBOOK_XML)
        workbook.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS_XML)
        workbook.writestr("xl/styles.xml", STYLES_XML)

        sheet_rows = [
            f'<row r="1" ht="30" customHeight="1">{_inline_string_cell("A1", "DAILY CREW SCHEDULE", 1)}</row>',
            (
                f'<row r="2">{_inline_string_cell("A2", "Branch", 2)}'
                f'{_inline_string_cell("B2", branch_name, 2)}</row>'
            ),
            (
                f'<row r="3">{_inline_string_cell("A3", "Schedule date", 2)}'
                f'{_inline_string_cell("B3", schedule_date, 2)}</row>'
            ),
            (
                '<row r="5">'
                + "".join(
                    _inline_string_cell(f"{_column_name(index)}5", label, 3)
                    for index, label in enumerate(
                        ("Station", "Crew Member", "Schedule"),
                        start=1,
                    )
                )
                + "</row>"
            ),
        ]

        station_merges = []
        row_number = 6
        entry_index = 0
        while entry_index < len(rows):
            station = rows[entry_index]["station"]
            group_end = entry_index + 1
            while group_end < len(rows) and rows[group_end]["station"] == station:
                group_end += 1
            first_row = row_number
            for row in rows[entry_index:group_end]:
                values = (station, row["crew"], row["schedule"])
                cells = []
                for column_index, value in enumerate(values, start=1):
                    style = 7 if column_index == 1 else 4
                    if column_index == 1 and row_number != first_row:
                        value = ""
                    cells.append(
                        _inline_string_cell(
                            f"{_column_name(column_index)}{row_number}",
                            value,
                            style,
                        )
                    )
                sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
                row_number += 1
            if row_number - first_row > 1:
                station_merges.append(
                    f'<mergeCell ref="A{first_row}:A{row_number - 1}"/>'
                )
            entry_index = group_end

        last_row = max(6, row_number - 1)
        merged_cells = ['<mergeCell ref="A1:C1"/>', *station_merges]
        worksheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:C{last_row}"/>
<sheetViews><sheetView workbookViewId="0"><pane ySplit="5" topLeftCell="A6" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="A6" sqref="A6"/></sheetView></sheetViews>
<cols><col min="1" max="1" width="24" customWidth="1"/><col min="2" max="2" width="34" customWidth="1"/><col min="3" max="3" width="28" customWidth="1"/></cols>
<sheetData>{''.join(sheet_rows)}</sheetData>
<autoFilter ref="A5:C{last_row}"/>
<mergeCells count="{len(merged_cells)}">{''.join(merged_cells)}</mergeCells>
</worksheet>"""
        workbook.writestr("xl/worksheets/sheet1.xml", worksheet_xml)

    return output.getvalue()
