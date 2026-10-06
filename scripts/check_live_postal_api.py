from services.live_postal_service import health, lookup_pincode, search

print("Health:", health())
rows, meta = lookup_pincode("560034")
print("PIN 560034 meta:", meta)
print("PIN 560034 first row:", rows[0] if rows else "NO DATA")
rows, meta = search("Koramangala", limit=5)
print("Search meta:", meta)
print("Search first row:", rows[0] if rows else "NO DATA")
