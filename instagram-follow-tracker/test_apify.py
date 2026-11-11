"""
Standalone Apify test script - tests the actor independently from the tracker.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_apify():
    print("=" * 60)
    print("APIFY STANDALONE TEST")
    print("=" * 60)

    # Check for API token
    token = os.getenv('APIFY_API_TOKEN')
    if not token:
        print("ERROR: APIFY_API_TOKEN not found in .env file")
        return

    print(f"[OK] API Token found: {token[:20]}...{token[-5:]}")

    # Import Apify client
    try:
        from apify_client import ApifyClient
        print("[OK] apify-client imported successfully")
    except ImportError:
        print("ERROR: apify-client not installed. Run: pip install apify-client")
        return

    # Initialize client
    client = ApifyClient(token)
    actor_id = "louisdeconinck/instagram-following-scraper"

    print(f"\n[TEST] Actor: {actor_id}")
    print("-" * 60)

    # Test username - change this to test different accounts
    test_username = "instagram"

    # Input configuration for louisdeconinck actor
    # This actor uses "usernames" (plural) as an array
    run_input = {
        "usernames": [test_username],
        "limit": 100  # Limit to 100 for testing
    }

    print(f"[INPUT] {run_input}")
    print(f"\n[RUNNING] Starting actor for @{test_username}...")
    print("(This may take 1-3 minutes...)\n")

    try:
        # Run the actor
        run = client.actor(actor_id).call(run_input=run_input)

        print(f"[OK] Actor run completed!")
        print(f"[INFO] Run ID: {run.get('id', 'N/A')}")
        print(f"[INFO] Status: {run.get('status', 'N/A')}")
        print(f"[INFO] Dataset ID: {run.get('defaultDatasetId', 'N/A')}")

        # Fetch results
        print(f"\n[FETCHING] Getting results from dataset...")

        results = list(client.dataset(run["defaultDatasetId"]).iterate_items())

        print(f"\n{'=' * 60}")
        print(f"RESULTS: {len(results)} items returned")
        print(f"{'=' * 60}")

        if len(results) == 0:
            print("\nWARNING: Apify returned 0 results!")
            print("Possible causes:")
            print("  - Account may be private")
            print("  - Rate limiting by Instagram")
            print("  - Invalid username")
            print("  - Actor configuration issue")
            print(f"\nCheck the Apify console for details:")
            print(f"  https://console.apify.com/actors/runs/{run.get('id', '')}")
        else:
            # Show first 5 results with all fields
            print("\n[SAMPLE] First 5 results (raw data):\n")
            for i, item in enumerate(results[:5]):
                print(f"--- Item {i+1} ---")
                for key, value in item.items():
                    print(f"  {key}: {value}")
                print()

            # Show what fields are available
            if results:
                print(f"[FIELDS] Available fields in response:")
                print(f"  {list(results[0].keys())}")

            # Show how we would extract the ID
            print(f"\n[ID EXTRACTION TEST]")
            for item in results[:3]:
                user_id = str(item.get('id') or item.get('pk') or item.get('userId') or item.get('username', ''))
                username = item.get('username', '')
                print(f"  ID: '{user_id}' | Username: '@{username}'")

        return results

    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    test_apify()
