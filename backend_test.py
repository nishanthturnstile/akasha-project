"""Backend API tests for Akasha Railway MVP Slice 0.

Tests all skeleton endpoints and verifies negative cases (404s for unimplemented endpoints).
"""
import requests
import sys
from typing import Dict, Any, List

BASE_URL = "https://railway-mvp-slice.preview.emergentagent.com"


class Slice0APITester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.failures: List[str] = []

    def test(self, name: str, fn) -> bool:
        """Run a single test and track results."""
        self.tests_run += 1
        print(f"\n{'='*60}")
        print(f"TEST {self.tests_run}: {name}")
        print('='*60)
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

    # ========================================================================
    # Positive tests
    # ========================================================================

    def test_api_health(self):
        """GET /api/health returns 200 with status='ok', service='api', slice=0."""
        def run():
            r = requests.get(f"{BASE_URL}/api/health", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            print(f"Response: {data}")
            
            self.assert_eq(data.get("status"), "ok", "status field")
            self.assert_eq(data.get("service"), "api", "service field")
            self.assert_eq(data.get("slice"), 0, "slice field")
            self.assert_in("version", data, "version field missing")
            self.assert_in("app", data, "app field missing")
            
        self.test("GET /api/health", run)

    def test_skeleton_services(self):
        """GET /api/_skeleton/services returns 200 with 7 services."""
        def run():
            r = requests.get(f"{BASE_URL}/api/_skeleton/services", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            print(f"Service count: {data.get('count')}")
            
            services = data.get("services", [])
            self.assert_eq(len(services), 7, "Should have exactly 7 services")
            
            # Check service IDs
            service_ids = [s["id"] for s in services]
            expected_ids = ["web", "api", "titiler", "stac-api", "postgis", "minio", "ingestion-worker"]
            self.assert_eq(sorted(service_ids), sorted(expected_ids), "Service IDs")
            
            # Check 'web' is the only public service
            public_services = [s for s in services if s.get("public")]
            self.assert_eq(len(public_services), 1, "Only 'web' should be public")
            self.assert_eq(public_services[0]["id"], "web", "Public service should be 'web'")
            
            # Check 'api' service has status='live'
            api_service = next((s for s in services if s["id"] == "api"), None)
            if not api_service:
                raise AssertionError("'api' service not found")
            self.assert_eq(api_service.get("status"), "live", "'api' service should be 'live'")
            
            # Check other services have status='defined'
            for s in services:
                if s["id"] != "api":
                    self.assert_eq(s.get("status"), "defined", f"{s['id']} should be 'defined'")
            
            print(f"✓ All 7 services present")
            print(f"✓ Only 'web' is public")
            print(f"✓ 'api' is live, others are defined")
            
        self.test("GET /api/_skeleton/services", run)

    def test_skeleton_manifest(self):
        """GET /api/_skeleton/manifest returns 200 with required fields."""
        def run():
            r = requests.get(f"{BASE_URL}/api/_skeleton/manifest", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            
            # Check pinnedImages
            pinned = data.get("pinnedImages", {})
            self.assert_in("ghcr.io/developmentseed/titiler:1.0.0", pinned.values(), 
                          "TiTiler image not in pinnedImages")
            self.assert_in("ghcr.io/stac-utils/stac-fastapi-pgstac:5.0.2", pinned.values(),
                          "STAC API image not in pinnedImages")
            print(f"✓ pinnedImages contains {len(pinned)} images")
            
            # Check roadmap has 8 entries
            roadmap = data.get("roadmap", [])
            self.assert_eq(len(roadmap), 8, "Roadmap should have 8 entries")
            
            # Check slice0 is active
            slice0 = next((r for r in roadmap if r.get("id") == "slice0"), None)
            if not slice0:
                raise AssertionError("slice0 not found in roadmap")
            self.assert_eq(slice0.get("status"), "active", "slice0 should be active")
            print(f"✓ Roadmap has 8 entries, slice0 is active")
            
            # Check inScope and outOfScope are non-empty
            in_scope = data.get("inScope", [])
            out_scope = data.get("outOfScope", [])
            if not in_scope:
                raise AssertionError("inScope is empty")
            if not out_scope:
                raise AssertionError("outOfScope is empty")
            print(f"✓ inScope: {len(in_scope)} items, outOfScope: {len(out_scope)} items")
            
            # Check repoTree exists
            repo_tree = data.get("repoTree")
            if repo_tree is None:
                print("⚠ repoTree is null (expected in container)")
            else:
                print(f"✓ repoTree present with {len(repo_tree)} top-level dirs")
            
        self.test("GET /api/_skeleton/manifest", run)

    def test_skeleton_env_matrix(self):
        """GET /api/_skeleton/env-matrix returns 200 with services object."""
        def run():
            r = requests.get(f"{BASE_URL}/api/_skeleton/env-matrix", timeout=10)
            self.assert_status(r, 200)
            
            data = r.json()
            services = data.get("services", {})
            
            # Check required services are present
            required = ["api", "titiler", "stac-api"]
            for svc in required:
                if svc not in services:
                    raise AssertionError(f"'{svc}' not in services object")
            
            print(f"✓ Services object includes: {', '.join(services.keys())}")
            
            # Check values are placeholders (contain '<' or are empty)
            api_vars = services.get("api", {})
            if not api_vars:
                raise AssertionError("api service has no variables")
            
            # Sample check: DATABASE_URL should be a placeholder
            db_url = api_vars.get("DATABASE_URL", "")
            if "<" not in db_url:
                print(f"⚠ DATABASE_URL might not be a placeholder: {db_url}")
            else:
                print(f"✓ Values are placeholders (e.g., DATABASE_URL contains '<')")
            
        self.test("GET /api/_skeleton/env-matrix", run)

    # ========================================================================
    # Negative tests (404s for unimplemented endpoints)
    # ========================================================================

    def test_api_config_404(self):
        """GET /api/config should return 404 (not implemented in Slice 0)."""
        def run():
            r = requests.get(f"{BASE_URL}/api/config", timeout=10)
            self.assert_status(r, 404)
            print("✓ Correctly returns 404 (not implemented)")
            
        self.test("GET /api/config (expect 404)", run)

    def test_api_sources_404(self):
        """GET /api/sources should return 404 (not implemented in Slice 0)."""
        def run():
            r = requests.get(f"{BASE_URL}/api/sources", timeout=10)
            self.assert_status(r, 404)
            print("✓ Correctly returns 404 (not implemented)")
            
        self.test("GET /api/sources (expect 404)", run)

    def test_api_indices_statistics_404(self):
        """POST /api/indices/statistics should return 404 (not implemented in Slice 0)."""
        def run():
            r = requests.post(
                f"{BASE_URL}/api/indices/statistics",
                json={"test": "data"},
                timeout=10
            )
            self.assert_status(r, 404)
            print("✓ Correctly returns 404 (not implemented)")
            
        self.test("POST /api/indices/statistics (expect 404)", run)

    # ========================================================================
    # Run all tests
    # ========================================================================

    def run_all(self):
        """Run all tests and print summary."""
        print("\n" + "="*60)
        print("AKASHA SLICE 0 BACKEND API TEST SUITE")
        print("="*60)
        
        # Positive tests
        self.test_api_health()
        self.test_skeleton_services()
        self.test_skeleton_manifest()
        self.test_skeleton_env_matrix()
        
        # Negative tests
        self.test_api_config_404()
        self.test_api_sources_404()
        self.test_api_indices_statistics_404()
        
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"Total tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        
        if self.failures:
            print("\n❌ FAILURES:")
            for f in self.failures:
                print(f"  - {f}")
        else:
            print("\n✅ ALL TESTS PASSED!")
        
        print("="*60)
        
        return 0 if self.tests_passed == self.tests_run else 1


if __name__ == "__main__":
    tester = Slice0APITester()
    sys.exit(tester.run_all())
