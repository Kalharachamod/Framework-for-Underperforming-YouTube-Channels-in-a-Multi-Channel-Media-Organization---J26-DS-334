"""Offline audit safety checks; no database or .env access."""
import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).resolve().parents[2] / "research/component_1/audit_data.py"
spec = importlib.util.spec_from_file_location("c1_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def test_rejects_wrong_role_or_writable_transaction_before_schema(self):
        for role, readonly in ((False, True), (True, False)):
            conn = MagicMock()
            conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {
                "expected_role": role, "read_only": readonly}
            with patch.object(audit, "inspect_schema") as inspect, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(ValueError):
                    audit.run_audit(conn)
                inspect.assert_not_called()

    def test_connection_failure_never_discloses_credentials(self):
        out = io.StringIO()
        with patch.object(audit, "load_dotenv"), patch.dict("os.environ", {"COMPONENT1_DB_URL": "FAKE_SECRET"}), patch.object(audit.psycopg, "connect", side_effect=audit.psycopg.OperationalError("FAKE_SECRET")), contextlib.redirect_stdout(out):
            self.assertEqual(audit.main(), 1)
        self.assertNotIn("FAKE_SECRET", out.getvalue())

    def test_missing_url_does_not_connect(self):
        with patch.object(audit, "load_dotenv"), patch.dict("os.environ", {"COMPONENT1_DB_URL": ""}), patch.object(audit.psycopg, "connect") as connect, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(audit.main(), 1)
            connect.assert_not_called()

    def test_generated_table_queries_are_selects_and_use_intended_grain(self):
        columns = [{"column_name": n, "data_type": t} for n, t in (
            ("video_id", "text"), ("collected_at", "timestamp with time zone"), ("view_count", "bigint"))]
        cur = MagicMock()
        cur.fetchall.return_value = [{"missing": 0}]
        result = audit.audit_table(cur, "video_stats_history", columns, ["video_id", "collected_at"])
        self.assertEqual(result["intended_grain"], ["video_id", "collected_at"])
        for call in cur.execute.call_args_list:
            statement = call.args[0].as_string(None).lstrip()
            self.assertTrue(statement.startswith(("SELECT", "WITH")))
            self.assertNotIn("FAKE_SECRET", statement)


if __name__ == "__main__":
    unittest.main()
