#!/bin/bash
cd /home/adminweihuzb/gswang/ibe_compliance_python
source venv/bin/activate
export HF_HUB_OFFLINE=1
uvicorn app:app --host 0.0.0.0 --port 12342 --workers 4
