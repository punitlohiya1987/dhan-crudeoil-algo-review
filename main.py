# DHAN CLOUD GLOBAL VARIABLES ISOLATION TEST
# Temporary diagnostic only. This file does not connect to Dhan,
# fetch data, monitor positions, or place/modify/cancel orders.

client_id = "{{CLIENT_ID}}"
access_token = "{{ACCESS_TOKEN}}"

client_id_unresolved = (
    client_id == "{{CLIENT_ID}}"
    or (client_id.startswith("{{") and client_id.endswith("}}"))
)
access_token_unresolved = (
    access_token == "{{ACCESS_TOKEN}}"
    or (access_token.startswith("{{") and access_token.endswith("}}"))
)

print("GLOBAL_VARIABLE_PROBE: reached main.py")
print("CLIENT_ID: " + ("UNRESOLVED" if client_id_unresolved else "SUBSTITUTED"))
print("ACCESS_TOKEN: " + ("UNRESOLVED" if access_token_unresolved else "SUBSTITUTED"))
print("No credential values or lengths are displayed.")
print("No Dhan API connection attempted; no orders possible.")
