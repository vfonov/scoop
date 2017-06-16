# Worker requests
INIT = b"I"
REQUEST = b"RQ"
TASK = b"T"
REPLY = b"RP"
SHUTDOWN = b"S"
VARIABLE = b"V"
BROKER_INFO = b"B"
STATUS_READY = b"SD"
RESEND_FUTURE = b"RF"
HEARTBEAT = b"HB"
REQUEST_STATUS_REQUEST = b"RSR"
REQUEST_STATUS_ANS = b"RSA"
REQUEST_INPROCESS = b"RI"
REQUEST_UNKNOWN = b"RU"

# Task statuses
STATUS_HERE = b"H"
STATUS_GIVEN = b"G"
STATUS_NONE = b"N"

# Broker interconnection
CONNECT = b"C"