"""Backend API tests for Akasha Railway MVP Slice 2 (Phase 2 raster de-risk).

Tests all product endpoints and verifies error handling. Note: 503 RASTER_BACKEND_UNAVAILABLE
is EXPECTED behavior in this environment (no MinIO/TiTiler/COGs) and is treated as PASS.
"""
import requests
import sys
from typing import Dict, Any, List

BASE_URL = "https://railway-mvp-slice.preview.emergentagent.com"


class Slice2APITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.failures: List[str] = []

    def test(self, name: str, fn) -> bool:
        """Run a single test and track results."""
        self.tests_run += 1
        print(f"\n{'='*70}")
        print(f"TEST {self.tests_run}: {name}")
        print('='*70)
        try:
            fn()
            self.tests_passed += 1
            print(f"✅ PASSED")
            return True
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            self.failures.append(f"{name}: {e}")
            return False
        except Exception as e:
            print(f"❌ ERROR: {e}")
            self.failures.append(f"{name}: {e}")
            return False

    def assert_eq(self, actual, expected, msg=""):
        """Assert equality with helpful message."""
        if actual != expected:
            raise AssertionError(f"{msg}\n  Expected: {expected}\n  Got: {actual}")

    def assert_in(self, item, container, msg=""):
        """Assert item is in container."""
        if item not in container:
            raise AssertionError(f"{msg}\n  Expected '{item}' to be in {container}")

    def assert_status(self, response: requests.Response, expected: int):
        """Assert HTTP status code."""
        if response.status_code != expected:
            raise AssertionError(
                f"Expected status {expected}, got {response.status_code}\n"
                f"Response: {response.text[:500]}"
            )

    def assert_error_shape(self, data: Dict[str, Any], expected_code: str):
        """Assert standard error response shape: {"error": {"code": ..., "message": ..., "details": ...}}"""
        if "error" not in data:
            raise AssertionError(f"Response missing 'error' key. Got: {data}")
        
        error = data["error"]
        if not isinstance(error, dict):
            raise AssertionError(f"'error' should be a dict. Got: {type(error)}")
        
        if "code" not in error:
            raise AssertionError(f"Error missing 'code' key. Got: {error}")
        if "message" not in error:
            raise AssertionError(f"Error missing 'message' key. Got: {error}")
        if "details" not in error:
            raise AssertionError(f"Error missing 'details' key. Got: {error}")
        
        if error["code"] != expected_code:
            raise AssertionError(f"Expected error code '{expected_code}', got '{error['code']}'")
        
        print(f"✓ Error shape valid: code={error['code']}, message={error['message'][:50]}...")

    # ========================================================================
    # Health & Config
    # ========================================================================

    def test_api_health(self):
        """GET /api/health returns 200 with status field."""
        def run():
            r = requests.get(f"{BASE_URL}/api/health", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            print(f"Response: {data}")
            
            self.assert_in("status", data, "status field missing")
            print(f"✓ Health endpoint returns status: {data['status']}")
            
        self.test("GET /api/health", run)

    def test_api_config(self):
        """GET /api/config returns 200 with required config fields."""
        def run():
            r = requests.get(f"{BASE_URL}/api/config", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            print(f"Response keys: {list(data.keys())}")
            
            # Check supportedIndices
            supported = data.get("supportedIndices", [])
            expected_indices = ['NDVI', 'NDRE', 'NDMI', 'NDWI_GREEN_NIR']
            self.assert_eq(supported, expected_indices, "supportedIndices")
            print(f"✓ supportedIndices: {supported}")
            
            # Check defaultIndex
            self.assert_eq(data.get("defaultIndex"), "NDVI", "defaultIndex")
            print(f"✓ defaultIndex: NDVI")
            
            # Check maxPolygonAreaHa
            max_area = data.get("maxPolygonAreaHa")
            self.assert_eq(max_area, 50, "maxPolygonAreaHa")
            print(f"✓ maxPolygonAreaHa: {max_area}")
            
            # Check aoi.id
            aoi = data.get("aoi", {})
            self.assert_eq(aoi.get("id"), "bangalore", "aoi.id")
            print(f"✓ aoi.id: {aoi.get('id')}")
            
        self.test("GET /api/config", run)

    # ========================================================================
    # Sources & Dates
    # ========================================================================

    def test_api_sources(self):
        """GET /api/sources returns 200 with sentinel-2-l2a source."""
        def run():
            r = requests.get(f"{BASE_URL}/api/sources", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            if not isinstance(data, list):
                raise AssertionError(f"Expected list, got {type(data)}")
            
            if len(data) == 0:
                raise AssertionError("Sources list is empty")
            
            first = data[0]
            print(f"First source: {first}")
            
            self.assert_eq(first.get("id"), "sentinel-2-l2a", "first source id")
            self.assert_in("supportedIndices", first, "supportedIndices missing")
            print(f"✓ First source id: {first['id']}")
            print(f"✓ supportedIndices: {first['supportedIndices']}")
            
        self.test("GET /api/sources", run)

    def test_api_source_dates(self):
        """GET /api/sources/sentinel-2-l2a/dates returns 200 with 2025-09-14."""
        def run():
            r = requests.get(f"{BASE_URL}/api/sources/sentinel-2-l2a/dates", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            if not isinstance(data, list):
                raise AssertionError(f"Expected list, got {type(data)}")
            
            print(f"Dates count: {len(data)}")
            
            # Check if 2025-09-14 is in the list
            dates = [d.get("acquisitionDate") for d in data]
            if "2025-09-14" not in dates:
                raise AssertionError(f"Expected '2025-09-14' in dates, got: {dates}")
            
            print(f"✓ Found acquisition date: 2025-09-14")
            
            # Check structure of first date entry
            if data:
                first = data[0]
                print(f"First date entry: {first}")
                self.assert_in("acquisitionDate", first, "acquisitionDate missing")
            
        self.test("GET /api/sources/sentinel-2-l2a/dates", run)

    def test_api_source_dates_unknown(self):
        """GET /api/sources/UNKNOWN/dates returns 404 with proper error shape."""
        def run():
            r = requests.get(f"{BASE_URL}/api/sources/UNKNOWN/dates", timeout=10)
            self.assert_status(r, 404)
            
            data = r.json()
            print(f"Error response: {data}")
            
            # Error code should be UNKNOWN_SOURCE or NO_ITEMS
            error_code = data.get("error", {}).get("code", "")
            if error_code not in ["UNKNOWN_SOURCE", "NO_ITEMS"]:
                raise AssertionError(f"Expected error code UNKNOWN_SOURCE or NO_ITEMS, got: {error_code}")
            
            self.assert_error_shape(data, error_code)
            
        self.test("GET /api/sources/UNKNOWN/dates (expect 404)", run)

    # ========================================================================
    # Layers
    # ========================================================================

    def test_api_layers_default(self):
        """GET /api/layers/default returns 200 with correct layer metadata."""
        def run():
            r = requests.get(f"{BASE_URL}/api/layers/default", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            print(f"Layer data: {data}")
            
            # Check sourceId
            self.assert_eq(data.get("sourceId"), "sentinel-2-l2a", "sourceId")
            print(f"✓ sourceId: {data['sourceId']}")
            
            # Check acquisitionDate
            self.assert_eq(data.get("acquisitionDate"), "2025-09-14", "acquisitionDate")
            print(f"✓ acquisitionDate: {data['acquisitionDate']}")
            
            # Check tileUrlTemplate
            expected_template = "/api/tiles/sentinel-2-l2a/2025-09-14/rgb/{z}/{x}/{y}.png"
            self.assert_eq(data.get("tileUrlTemplate"), expected_template, "tileUrlTemplate")
            print(f"✓ tileUrlTemplate: {data['tileUrlTemplate']}")
            
        self.test("GET /api/layers/default", run)

    # ========================================================================
    # Statistics - Error Cases
    # ========================================================================

    def test_statistics_invalid_geometry(self):
        """POST /api/indices/statistics with Point geometry returns 422 INVALID_GEOMETRY."""
        def run():
            payload = {
                "geometry": {
                    "type": "Point",
                    "coordinates": [78.2, 12.1]
                },
                "sourceId": "sentinel-2-l2a",
                "acquisitionDate": "2025-09-14",
                "indexType": "NDVI"
            }
            
            r = requests.post(f"{BASE_URL}/api/indices/statistics", json=payload, timeout=10)
            self.assert_status(r, 422)
            
            data = r.json()
            print(f"Error response: {data}")
            
            self.assert_error_shape(data, "INVALID_GEOMETRY")
            
        self.test("POST /api/indices/statistics - invalid geometry (Point)", run)

    def test_statistics_unsupported_index(self):
        """POST /api/indices/statistics with unsupported index returns 400 UNSUPPORTED_INDEX."""
        def run():
            payload = {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.105], [78.2, 12.1]]]
                },
                "sourceId": "sentinel-2-l2a",
                "acquisitionDate": "2025-09-14",
                "indexType": "NOPE"
            }
            
            r = requests.post(f"{BASE_URL}/api/indices/statistics", json=payload, timeout=10)
            self.assert_status(r, 400)
            
            data = r.json()
            print(f"Error response: {data}")
            
            self.assert_error_shape(data, "UNSUPPORTED_INDEX")
            
        self.test("POST /api/indices/statistics - unsupported index", run)

    def test_statistics_polygon_too_large(self):
        """POST /api/indices/statistics with oversized polygon returns 413 POLYGON_TOO_LARGE."""
        def run():
            # Create a ~1deg x 1deg box (way too large)
            payload = {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[78.0, 12.0], [79.0, 12.0], [79.0, 13.0], [78.0, 13.0], [78.0, 12.0]]]
                },
                "sourceId": "sentinel-2-l2a",
                "acquisitionDate": "2025-09-14",
                "indexType": "NDVI"
            }
            
            r = requests.post(f"{BASE_URL}/api/indices/statistics", json=payload, timeout=10)
            self.assert_status(r, 413)
            
            data = r.json()
            print(f"Error response: {data}")
            
            self.assert_error_shape(data, "POLYGON_TOO_LARGE")
            
        self.test("POST /api/indices/statistics - polygon too large", run)

    # ========================================================================
    # Statistics & Tiles - Expected 503 (RASTER_BACKEND_UNAVAILABLE)
    # ========================================================================

    def test_statistics_valid_polygon_503(self):
        """POST /api/indices/statistics with valid polygon returns 503 RASTER_BACKEND_UNAVAILABLE (EXPECTED)."""
        def run():
            payload = {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[78.2, 12.1], [78.205, 12.1], [78.205, 12.105], [78.2, 12.105], [78.2, 12.1]]]
                },
                "sourceId": "sentinel-2-l2a",
                "acquisitionDate": "2025-09-14",
                "indexType": "NDVI"
            }
            
            r = requests.post(f"{BASE_URL}/api/indices/statistics", json=payload, timeout=10)
            self.assert_status(r, 503)
            
            data = r.json()
            print(f"Error response: {data}")
            
            self.assert_error_shape(data, "RASTER_BACKEND_UNAVAILABLE")
            print("✓ EXPECTED 503 - MinIO/COGs not available in this environment")
            
        self.test("POST /api/indices/statistics - valid polygon (EXPECT 503)", run)

    def test_tiles_rgb_503(self):
        """GET /api/tiles/.../rgb/... returns 503 RASTER_BACKEND_UNAVAILABLE (EXPECTED)."""
        def run():
            r = requests.get(
                f"{BASE_URL}/api/tiles/sentinel-2-l2a/2025-09-14/rgb/12/2937/1881.png",
                timeout=10
            )
            self.assert_status(r, 503)
            
            # For tile endpoint, response might be JSON error or empty
            try:
                data = r.json()
                print(f"Error response: {data}")
                self.assert_error_shape(data, "RASTER_BACKEND_UNAVAILABLE")
            except:
                # If not JSON, that's also acceptable for 503
                print(f"✓ Got 503 (non-JSON response)")
            
            print("✓ EXPECTED 503 - TiTiler/MinIO not available in this environment")
            
        self.test("GET /api/tiles/.../rgb/... (EXPECT 503)", run)

    # ========================================================================
    # Regression - Slice 0 endpoints still work
    # ========================================================================

    def test_skeleton_services_regression(self):
        """GET /api/_skeleton/services still returns 200 (Slice 0 unchanged)."""
        def run():
            r = requests.get(f"{BASE_URL}/api/_skeleton/services", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            services = data.get("services", [])
            print(f"✓ Services count: {len(services)}")
            
        self.test("GET /api/_skeleton/services (regression)", run)

    def test_skeleton_manifest_regression(self):
        """GET /api/_skeleton/manifest still returns 200 (Slice 0 unchanged)."""
        def run():
            r = requests.get(f"{BASE_URL}/api/_skeleton/manifest", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            print(f"✓ Manifest keys: {list(data.keys())}")
            
        self.test("GET /api/_skeleton/manifest (regression)", run)

    # ========================================================================
    # Run all tests
    # ========================================================================

    def run_all(self):
        """Run all tests and print summary."""
        print("\n" + "="*70)
        print("AKASHA SLICE 2 (PHASE 2 RASTER DE-RISK) BACKEND API TEST SUITE")
        print("="*70)
        print("NOTE: 503 RASTER_BACKEND_UNAVAILABLE is EXPECTED (no MinIO/COGs)")
        print("="*70)
        
        # Health & Config
        self.test_api_health()
        self.test_api_config()
        
        # Sources & Dates
        self.test_api_sources()
        self.test_api_source_dates()
        self.test_api_source_dates_unknown()
        
        # Layers
        self.test_api_layers_default()
        
        # Statistics - Error Cases
        self.test_statistics_invalid_geometry()
        self.test_statistics_unsupported_index()
        self.test_statistics_polygon_too_large()
        
        # Statistics & Tiles - Expected 503
        self.test_statistics_valid_polygon_503()
        self.test_tiles_rgb_503()
        
        # Regression
        self.test_skeleton_services_regression()
        self.test_skeleton_manifest_regression()
        
        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        
        if self.failures:
            print("\n❌ FAILURES:")
            for f in self.failures:
                print(f"  - {f}")
        else:
            print("\n✅ ALL TESTS PASSED!")
        
        print("="*70)
        
        return 0 if self.tests_passed == self.tests_run else 1


if __name__ == "__main__":
    tester = Slice2APITester()
    sys.exit(tester.run_all())
