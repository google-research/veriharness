# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# A plain document-work environment for benchmarks whose original world is a set of
# files (mounted read-only under the data root): Python with the document libraries
# the skills use, plus LibreOffice for spreadsheet recalculation.
#   docker build -f harness/env/Dockerfile.apex -t veriharness-docs .
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-calc libreoffice-writer curl git sqlite3 poppler-utils zip unzip xxd \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir openpyxl xlrd python-docx python-pptx pymupdf pdfplumber pypdf PyPDF2 \
    pandas numpy scipy statsmodels matplotlib reportlab tabulate
