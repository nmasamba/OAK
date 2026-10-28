# SPDX-License-Identifier: Apache-2.0
"""HTTP API adapter.

Nothing is imported here: importing `oak.interfaces.api.server` would otherwise build the
application, and reach the database configuration, before the entrypoint has set up its
logging. uvicorn and the tests import `oak.interfaces.api.app` themselves.
"""
