"""Tests for Watchtower data source client."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from argus.sources.watchtower import WatchtowerClient


@pytest.fixture
def client():
    """Create a WatchtowerClient with test URLs."""
    return WatchtowerClient(
        loki_url="http://localhost:3100",
        tempo_url="http://localhost:3200",
        prometheus_url="http://localhost:9090",
        sonarqube_url="http://localhost:9000",
        sonarqube_token="test-token",
        timeout=5.0,
    )


class TestHealthChecks:
    """Test service health check methods."""

    @pytest.mark.asyncio
    async def test_check_loki_health_success(self, client) -> None:
        """check_loki_health returns True when healthy."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            healthy, latency = await client.check_loki_health()

            assert healthy is True
            assert latency > 0
            mock_instance.get.assert_called_once_with("http://localhost:3100/ready")

    @pytest.mark.asyncio
    async def test_check_loki_health_failure(self, client) -> None:
        """check_loki_health returns False on failure."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = Exception("Connection refused")
            mock_client.return_value.__aenter__.return_value = mock_instance

            healthy, latency = await client.check_loki_health()

            assert healthy is False
            assert latency >= 0

    @pytest.mark.asyncio
    async def test_check_tempo_health_success(self, client) -> None:
        """check_tempo_health returns True when healthy."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            healthy, latency = await client.check_tempo_health()

            assert healthy is True
            mock_instance.get.assert_called_once_with("http://localhost:3200/ready")

    @pytest.mark.asyncio
    async def test_check_prometheus_health_success(self, client) -> None:
        """check_prometheus_health returns True when healthy."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            healthy, latency = await client.check_prometheus_health()

            assert healthy is True
            mock_instance.get.assert_called_once_with("http://localhost:9090/-/healthy")

    @pytest.mark.asyncio
    async def test_check_sonarqube_health_success(self, client) -> None:
        """check_sonarqube_health returns True when UP."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "UP"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            healthy, latency = await client.check_sonarqube_health()

            assert healthy is True

    @pytest.mark.asyncio
    async def test_check_sonarqube_health_not_up(self, client) -> None:
        """check_sonarqube_health returns False when not UP."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "DOWN"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            healthy, latency = await client.check_sonarqube_health()

            assert healthy is False


class TestLokiQueries:
    """Test Loki log query methods."""

    @pytest.mark.asyncio
    async def test_query_loki_logs(self, client) -> None:
        """query_loki_logs parses Loki response correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "result": [
                    {
                        "stream": {"service_name": "api", "level": "error"},
                        "values": [
                            ["1704067200000000000", "Error: Connection refused"],
                            ["1704067201000000000", "Error: Timeout"],
                        ],
                    }
                ]
            }
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            logs = await client.query_loki_logs('{service_name="api"} |= "error"')

            assert len(logs) == 2
            assert logs[0]["line"] == "Error: Connection refused"
            assert logs[0]["labels"]["service_name"] == "api"

    @pytest.mark.asyncio
    async def test_query_loki_errors_with_service(self, client) -> None:
        """query_loki_errors builds correct query with service filter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": {"result": []}}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            await client.query_loki_errors(service_name="api-gateway")

            # Verify the query was built correctly
            call_args = mock_instance.get.call_args
            assert "service_name" in call_args.kwargs["params"]["query"]

    @pytest.mark.asyncio
    async def test_query_loki_errors_with_error_code(self, client) -> None:
        """query_loki_errors includes error code filter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": {"result": []}}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            await client.query_loki_errors(error_code="ERR_500")

            call_args = mock_instance.get.call_args
            assert "ERR_500" in call_args.kwargs["params"]["query"]


class TestTempoQueries:
    """Test Tempo trace query methods."""

    @pytest.mark.asyncio
    async def test_search_traces(self, client) -> None:
        """search_traces parses Tempo response correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "traces": [
                {
                    "traceID": "abc123",
                    "rootServiceName": "frontend",
                    "rootTraceName": "GET /api/users",
                    "durationMs": 150,
                },
                {
                    "traceID": "def456",
                    "rootServiceName": "backend",
                    "rootTraceName": "POST /api/orders",
                    "durationMs": 320,
                },
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            traces = await client.search_traces()

            assert len(traces) == 2
            assert traces[0]["traceID"] == "abc123"
            assert traces[0]["durationMs"] == 150

    @pytest.mark.asyncio
    async def test_search_traces_with_filters(self, client) -> None:
        """search_traces applies service and duration filters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"traces": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            await client.search_traces(
                service_name="api",
                min_duration_ms=100,
                max_duration_ms=5000,
            )

            call_args = mock_instance.get.call_args
            params = call_args.kwargs["params"]
            assert "service.name" in params.get("tags", "")
            assert params.get("minDuration") == "100ms"
            assert params.get("maxDuration") == "5000ms"

    @pytest.mark.asyncio
    async def test_get_trace(self, client) -> None:
        """get_trace retrieves a full trace by ID."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "batches": [{"resource": {"serviceName": "api"}}]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            trace = await client.get_trace("abc123")

            assert trace is not None
            mock_instance.get.assert_called_once_with("http://localhost:3200/api/traces/abc123")

    @pytest.mark.asyncio
    async def test_get_trace_not_found(self, client) -> None:
        """get_trace returns None for 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            trace = await client.get_trace("nonexistent")

            assert trace is None

    @pytest.mark.asyncio
    async def test_search_error_traces(self, client) -> None:
        """search_error_traces filters by status.code=ERROR."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"traces": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            await client.search_error_traces()

            call_args = mock_instance.get.call_args
            params = call_args.kwargs["params"]
            assert 'status.code="ERROR"' in params["tags"]


class TestPrometheusQueries:
    """Test Prometheus metric query methods."""

    @pytest.mark.asyncio
    async def test_query_prometheus(self, client) -> None:
        """query_prometheus executes PromQL query."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"service": "api", "status_code": "500"},
                        "value": [1704067200, "0.05"],
                    }
                ]
            },
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            results = await client.query_prometheus('rate(http_requests_total[5m])')

            assert len(results) == 1
            assert results[0]["value"] == "0.05"
            assert results[0]["metric"]["service"] == "api"

    @pytest.mark.asyncio
    async def test_query_prometheus_error(self, client) -> None:
        """query_prometheus raises on error status."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "error": "invalid query",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            with pytest.raises(ValueError, match="invalid query"):
                await client.query_prometheus("bad{query")


class TestSonarQubeQueries:
    """Test SonarQube issue query methods."""

    @pytest.mark.asyncio
    async def test_get_sonarqube_issues(self, client) -> None:
        """get_sonarqube_issues fetches issues with auth."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "issues": [
                {
                    "key": "issue-001",
                    "rule": "squid:S1234",
                    "severity": "CRITICAL",
                    "component": "project:src/main.py",
                    "message": "Remove this unused variable",
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            issues = await client.get_sonarqube_issues("my-project")

            assert len(issues) == 1
            assert issues[0]["severity"] == "CRITICAL"
            # Verify auth header was set
            call_args = mock_instance.get.call_args
            assert "Authorization" in call_args.kwargs.get("headers", {})

    @pytest.mark.asyncio
    async def test_get_sonarqube_issues_with_filters(self, client) -> None:
        """get_sonarqube_issues applies severity and type filters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"issues": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            await client.get_sonarqube_issues(
                "my-project",
                severities=["CRITICAL", "BLOCKER"],
                types=["BUG"],
            )

            call_args = mock_instance.get.call_args
            params = call_args.kwargs["params"]
            assert params["severities"] == "CRITICAL,BLOCKER"
            assert params["types"] == "BUG"


class TestDataExport:
    """Test data export methods."""

    def test_write_logs_to_csv(self, client) -> None:
        """write_logs_to_csv creates CSV with correct format."""
        logs = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "line": "Error: Connection failed",
                "labels": {"service_name": "api", "level": "error"},
            },
            {
                "timestamp": "2024-01-01T00:00:01",
                "line": "Error: Timeout",
                "labels": {"service_name": "api", "level": "error"},
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "logs" / "test.csv"
            client.write_logs_to_csv(logs, csv_path)

            assert csv_path.exists()
            content = csv_path.read_text()
            assert "timestamp" in content
            assert "line" in content
            assert "service_name" in content
            assert "Connection failed" in content

    def test_write_logs_to_csv_empty(self, client) -> None:
        """write_logs_to_csv handles empty list gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "logs" / "empty.csv"
            client.write_logs_to_csv([], csv_path)
            # Should not create file for empty logs
            assert not csv_path.exists()

    def test_write_traces_to_csv(self, client) -> None:
        """write_traces_to_csv creates CSV with correct format."""
        traces = [
            {
                "traceID": "abc123",
                "rootServiceName": "frontend",
                "rootTraceName": "GET /api",
                "durationMs": 150,
                "startTimeUnixNano": 1704067200000000000,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "traces" / "test.csv"
            client.write_traces_to_csv(traces, csv_path)

            assert csv_path.exists()
            content = csv_path.read_text()
            assert "traceID" in content
            assert "rootServiceName" in content
            assert "abc123" in content

    def test_write_traces_to_csv_empty(self, client) -> None:
        """write_traces_to_csv handles empty list gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "traces" / "empty.csv"
            client.write_traces_to_csv([], csv_path)
            assert not csv_path.exists()
