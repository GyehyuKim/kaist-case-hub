# OCR Notes

- Source images: `01. Captures/*.png`, sorted by filename timestamp.
- Local OCR engine used: Windows OCR via `03. Tools/ocr_folder.ps1` and `03. Tools/ocr_windows.ps1`.
- Windows PowerShell 5.1 (`powershell.exe`) was used because PowerShell 7 could not load the Windows Runtime OCR types in this environment.
- Raw OCR output: `02. Outputs/lovepop.ocr.raw.txt`.
- Manual corrections were applied for OCR confusions such as `0f/of`, `t0/to`, `1/I`, `5/$`, broken years, names, schools, fund names, dollar amounts, percentages, and table labels.
- Exhibit tables were reconstructed only where values were legible in the screenshots. For chart exhibits without exact visible data labels, the Markdown records the title, source, note, and qualitative trend rather than invented monthly values.
- Footnote markers were not preserved individually because the screenshots do not include the corresponding footnote text.
