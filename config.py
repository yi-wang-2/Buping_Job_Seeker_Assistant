# In this file, you can set the configurations of the app.

import os
from pathlib import Path

from dotenv import load_dotenv

from src.utils.constants import DEBUG, ERROR, LLM_MODEL, OPENAI

# Load .env from project root if present
project_root = Path(__file__).resolve().parent
env_path = project_root.parent / '.env'
if env_path.exists():
	load_dotenv(env_path)

#config related to logging must have prefix LOG_
LOG_LEVEL = 'DEBUG'
LOG_SELENIUM_LEVEL = DEBUG
LOG_TO_FILE = True
LOG_TO_CONSOLE = True

MINIMUM_WAIT_TIME_IN_SECONDS = 60

JOB_APPLICATIONS_DIR = "job_applications"
JOB_SUITABILITY_SCORE = 7

JOB_MAX_APPLICATIONS = 5
JOB_MIN_APPLICATIONS = 1

LLM_MODEL_TYPE = os.environ.get('LLM_MODEL_TYPE', os.environ.get('LLM_MODEL_TYPE_DEF', 'anthropic'))
LLM_MODEL = os.environ.get('LLM_MODEL', 'MiniMax-M2.7')
# MiniMax uses Anthropic-compatible endpoint
LLM_API_URL = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.minimaxi.com/anthropic')

# Anthropic/MiniMax configuration
ANTHROPIC_AUTH_TOKEN = os.environ.get('ANTHROPIC_AUTH_TOKEN', 'sk-cp-shrFT60UliCZdN3bExya4P5R6qGsiWSibi60_1CuLPBCqS0vaH9qIE-nBaeKWL-wMKO_0L-SHlEUFkp-mQIrrscDSEmXa49gCcwSxLtuCMvO5XE1EYyVy3w')
ANTHROPIC_BASE_URL = os.environ.get('ANTHROPIC_BASE_URL', 'https://api.minimaxi.com/anthropic')
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'MiniMax-M2.7')

# Additional flags from user
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = os.environ.get('CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC', '1')

# Force LLM model selection to anthropic when configured
if ANTHROPIC_AUTH_TOKEN and ANTHROPIC_BASE_URL and ANTHROPIC_MODEL and LLM_MODEL_TYPE == 'anthropic':
	LLM_MODEL = ANTHROPIC_MODEL

# API timeout in milliseconds (string in .env allowed)
try:
	API_TIMEOUT_MS = int(os.environ.get('API_TIMEOUT_MS', '300000'))
except ValueError:
	API_TIMEOUT_MS = 300000
