"""Provider ports and adapters.

Every external system the backend talks to (LLM, object storage, realtime/
recording, email) is reached through an abstract *port* in this package and
a concrete *adapter* chosen by configuration in ``factory.py``. Application
code (routers, services) imports the port and the factory only -- never a
vendor SDK. docs/production-hardening-plan.md §1 rule 3, H1-B.
"""
