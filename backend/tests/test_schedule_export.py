import unittest
from datetime import time
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from docx import Document

from app.database import Base
from app.models.branch import Branch
from app.models.requirement import StaffingRequirement
from app.models.station import Station
from app.models.user import User, UserRole
from app.routers.schedule_exports import (
    export_schedule,
    export_schedule_docx,
    export_schedule_pdf,
)
from app.schemas.schedule_export import (
    ScheduleExportRequest,
    ScheduleExportRow,
)


class ScheduleExportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.branch = Branch(
            name="SM City & Legazpi",
            opening_time=time(8, 0),
            closing_time=time(22, 0),
        )
        self.other_branch = Branch(
            name="Other Branch",
            opening_time=time(8, 0),
            closing_time=time(22, 0),
        )
        self.session.add_all([self.branch, self.other_branch])
        self.session.flush()
        self.manager = User(
            email="manager@example.com",
            password_hash="test-hash",
            full_name="Branch Manager",
            role=UserRole.MANAGER,
            branch_id=self.branch.id,
        )
        self.employee = User(
            email="crew@example.com",
            password_hash="test-hash",
            full_name="Crew Member",
            role=UserRole.EMPLOYEE,
            branch_id=self.branch.id,
            crew_type="Crew Trainer",
            qualified_stations="1",
            is_active=True,
        )
        self.other_employee = User(
            email="other@example.com",
            password_hash="test-hash",
            full_name="Other Crew",
            role=UserRole.EMPLOYEE,
            branch_id=self.other_branch.id,
            is_active=True,
        )
        self.station = Station(
            branch_id=self.branch.id,
            name='Cashier <Front> & "Lobby"',
            opening_start_time=time(8, 0),
            opening_end_time=time(16, 0),
            mid_start_time=time(12, 0),
            mid_end_time=time(20, 0),
            closing_start_time=time(14, 0),
            closing_end_time=time(22, 0),
        )
        self.other_station = Station(branch_id=self.other_branch.id, name="Kitchen")
        self.session.add_all(
            [self.manager, self.employee, self.other_employee, self.station, self.other_station]
        )
        self.session.flush()
        self.employee.qualified_stations = str(self.station.id)
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch.id,
                station_id=self.station.id,
                shift_type="Opening",
                start_time=time(8, 0),
                end_time=time(16, 0),
                required_count=2,
            )
        )
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch.id,
                station_id=self.station.id,
                shift_type="Mid",
                start_time=time(12, 0),
                end_time=time(20, 0),
                required_count=1,
            )
        )
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch.id,
                station_id=self.station.id,
                shift_type="Closing",
                start_time=time(14, 0),
                end_time=time(22, 0),
                required_count=0,
            )
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_exports_branch_schedule_to_valid_excel_workbook(self):
        payload = ScheduleExportRequest(
            schedule_date="2026-11-04",
            rows=[
                ScheduleExportRow(
                    station_id=self.station.id,
                    shift_name="Mid",
                    assigned_user_ids=[],
                ),
                ScheduleExportRow(
                    station_id=self.station.id,
                    shift_name="Opening",
                    assigned_user_ids=[self.employee.id],
                ),
                ScheduleExportRow(
                    station_id=self.station.id,
                    shift_name="Closing",
                    assigned_user_ids=[],
                ),
            ],
        )

        response = export_schedule(payload, self.session, self.manager)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.media_type,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn(
            "smartshift-schedule-SM-City-Legazpi-2026-11-04.xlsx",
            response.headers["content-disposition"],
        )
        workbook = ZipFile(BytesIO(response.body))
        self.assertIsNone(workbook.testzip())
        for name in workbook.namelist():
            if name.endswith((".xml", ".rels")):
                ElementTree.fromstring(workbook.read(name))
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        values = [
            node.text
            for node in sheet.iter()
            if node.tag.endswith("}t") and node.text is not None
        ]
        self.assertIn("DAILY CREW SCHEDULE", values)
        self.assertIn(self.branch.name, values)
        self.assertIn("2026-11-04", values)
        self.assertIn(self.station.name, values)
        self.assertIn("Crew Member (Crew Trainer)", values)
        self.assertIn("Station", values)
        self.assertIn("Crew Member", values)
        self.assertIn("Schedule", values)
        self.assertIn("8:00 AM - 4:00 PM", values)
        self.assertIn("UNASSIGNED", values)
        self.assertNotIn("Opening", values)
        self.assertNotIn("Mid", values)
        self.assertNotIn("Closing", values)
        rows = sheet.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row")
        self.assertEqual(
            [row.attrib["r"] for row in rows if int(row.attrib["r"]) >= 6],
            ["6", "7"],
        )
        data_cells = [
            [
                node.find(
                    ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
                ).text
                for node in row.findall(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"
                )
            ]
            for row in rows
            if int(row.attrib["r"]) >= 6
        ]
        self.assertEqual(data_cells[0][1], "Crew Member (Crew Trainer)")
        self.assertEqual(data_cells[1][1], "UNASSIGNED")
        merges = sheet.findall(
            ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}mergeCell"
        )
        self.assertIn("A6:A7", [merge.attrib["ref"] for merge in merges])
        self.assertEqual(
            len([value for value in values if value == self.branch.name]),
            1,
        )

    def test_exports_compact_schedule_in_word_and_pdf_formats(self):
        payload = ScheduleExportRequest(
            schedule_date="2026-11-04",
            rows=[
                ScheduleExportRow(
                    station_id=self.station.id,
                    shift_name="Mid",
                    assigned_user_ids=[],
                ),
                ScheduleExportRow(
                    station_id=self.station.id,
                    shift_name="Opening",
                    assigned_user_ids=[self.employee.id],
                ),
                ScheduleExportRow(
                    station_id=self.station.id,
                    shift_name="Closing",
                    assigned_user_ids=[],
                ),
            ],
        )

        word_response = export_schedule_docx(payload, self.session, self.manager)
        self.assertEqual(word_response.status_code, 200)
        self.assertEqual(
            word_response.media_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertIn(".docx", word_response.headers["content-disposition"]        )
        word_document = Document(BytesIO(word_response.body))
        self.assertEqual(len(word_document.tables), 1)
        word_table = word_document.tables[0]
        self.assertEqual(
            [cell.text for cell in word_table.rows[0].cells],
            ["STATION", "CREW MEMBER", "SCHEDULE"],
        )
        self.assertEqual(
            word_table.rows[1].cells[1].text,
            "Crew Member (Crew Trainer)",
        )
        self.assertEqual(word_table.rows[1].cells[0].text, self.station.name)
        self.assertEqual(word_table.rows[1].cells[2].text, "8:00 AM - 4:00 PM")
        self.assertEqual(word_table.rows[2].cells[1].text, "UNASSIGNED")
        self.assertEqual(word_table._tbl.xml.count("w:vMerge"), 2)
        word_text = "\n".join(
            cell.text for row in word_table.rows for cell in row.cells
        )
        self.assertIn(
            "DAILY CREW SCHEDULE",
            "\n".join(paragraph.text for paragraph in word_document.paragraphs),
        )
        self.assertIn("Crew Member (Crew Trainer)", word_text)
        self.assertIn("UNASSIGNED", word_text)
        self.assertNotIn("Opening", word_text)
        self.assertNotIn("Mid", word_text)
        self.assertNotIn("Closing", word_text)

        pdf_response = export_schedule_pdf(payload, self.session, self.manager)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.media_type, "application/pdf")
        self.assertIn(".pdf", pdf_response.headers["content-disposition"])
        self.assertTrue(pdf_response.body.startswith(b"%PDF-"))
        self.assertTrue(pdf_response.body.rstrip().endswith(b"%%EOF"))

    def test_rejects_station_outside_manager_branch(self):
        payload = ScheduleExportRequest(
            schedule_date="2026-11-04",
            rows=[
                ScheduleExportRow(
                    station_id=self.other_station.id,
                    shift_name="Opening",
                    assigned_user_ids=[],
                )
            ],
        )

        for exporter in (
            export_schedule,
            export_schedule_docx,
            export_schedule_pdf,
        ):
            with self.subTest(exporter=exporter.__name__):
                with self.assertRaises(HTTPException) as raised:
                    exporter(payload, self.session, self.manager)
                self.assertEqual(raised.exception.status_code, 422)

    def test_rejects_crew_outside_manager_branch(self):
        payload = ScheduleExportRequest(
            schedule_date="2026-11-04",
            rows=[
                ScheduleExportRow(
                    station_id=self.station.id,
                    shift_name="Opening",
                    assigned_user_ids=[self.other_employee.id],
                )
            ],
        )

        with self.assertRaises(HTTPException) as raised:
            export_schedule(payload, self.session, self.manager)

        self.assertEqual(raised.exception.status_code, 422)

    def test_export_uses_name_without_empty_crew_type(self):
        self.employee.crew_type = "   "
        self.session.commit()
        payload = ScheduleExportRequest(
            schedule_date="2026-11-04",
            rows=[
                ScheduleExportRow(
                    station_id=self.station.id,
                    shift_name="Opening",
                    assigned_user_ids=[self.employee.id],
                )
            ],
        )

        response = export_schedule_docx(payload, self.session, self.manager)
        word_document = Document(BytesIO(response.body))
        rows = word_document.tables[0].rows

        self.assertEqual(rows[1].cells[1].text, "Crew Member")
        self.assertNotIn("()", rows[1].cells[1].text)

    def test_export_uses_standard_shift_names_with_configured_hours(self):
        opening = self.session.query(StaffingRequirement).filter_by(
            station_id=self.station.id,
            shift_type="Opening",
        ).one()
        opening.start_time = time(9, 0)
        opening.end_time = time(13, 0)
        self.session.commit()
        payload = ScheduleExportRequest(
            schedule_date="2026-11-04",
            rows=[
                ScheduleExportRow(
                    station_id=self.station.id,
                    shift_name="Opening",
                    assigned_user_ids=[self.employee.id],
                )
            ],
        )

        response = export_schedule_docx(payload, self.session, self.manager)
        document = Document(BytesIO(response.body))
        crew_row = document.tables[0].rows[1]

        self.assertEqual(crew_row.cells[1].text, "Crew Member (Crew Trainer)")
        self.assertEqual(crew_row.cells[2].text, "9:00 AM - 1:00 PM")

    def test_rejects_crew_not_qualified_for_station(self):
        self.employee.qualified_stations = None
        self.session.commit()
        payload = ScheduleExportRequest(
            schedule_date="2026-11-04",
            rows=[
                ScheduleExportRow(
                    station_id=self.station.id,
                    shift_name="Opening",
                    assigned_user_ids=[self.employee.id],
                )
            ],
        )

        with self.assertRaises(HTTPException) as raised:
            export_schedule(payload, self.session, self.manager)

        self.assertEqual(raised.exception.status_code, 422)

    def test_non_manager_cannot_export(self):
        with self.assertRaises(HTTPException) as raised:
            export_schedule(
                ScheduleExportRequest(
                    schedule_date="2026-11-04",
                    rows=[
                        ScheduleExportRow(
                            station_id=self.station.id,
                            shift_name="Opening",
                            assigned_user_ids=[],
                        )
                    ],
                ),
                self.session,
                self.employee,
            )

        self.assertEqual(raised.exception.status_code, 403)

    def test_schema_rejects_duplicate_station_shifts_and_crew(self):
        with self.assertRaises(ValueError):
            ScheduleExportRequest(
                schedule_date="2026-11-04",
                rows=[
                    ScheduleExportRow(
                        station_id=1,
                        shift_name="Opening",
                        assigned_user_ids=[1],
                    ),
                    ScheduleExportRow(
                        station_id=1,
                        shift_name="Opening",
                        assigned_user_ids=[],
                    ),
                ],
            )

        with self.assertRaises(ValueError):
            ScheduleExportRequest(
                schedule_date="2026-11-04",
                rows=[
                    ScheduleExportRow(
                        station_id=1,
                        shift_name="Opening",
                        assigned_user_ids=[1],
                    ),
                    ScheduleExportRow(
                        station_id=2,
                        shift_name="Mid",
                        assigned_user_ids=[1],
                    ),
                ],
            )


if __name__ == "__main__":
    unittest.main()
