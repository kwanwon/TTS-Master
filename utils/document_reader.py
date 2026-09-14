import os

class DocumentReader:
    @staticmethod
    def read_file(file_path):
        """지원되는 파일 형식(.txt, .docx, .pdf)을 읽어서 텍스트로 반환합니다."""
        ext = os.path.splitext(file_path)[1].lower()
        text = ""
        
        try:
            if ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
            elif ext == '.docx':
                try:
                    import docx
                    doc = docx.Document(file_path)
                    text = "\n".join([para.text for para in doc.paragraphs])
                except ImportError:
                    text = "[오류: python-docx 라이브러리가 설치되지 않았습니다.]"
            elif ext == '.pdf':
                try:
                    import pypdf
                    reader = pypdf.PdfReader(file_path)
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                except ImportError:
                    text = "[오류: pypdf 라이브러리가 설치되지 않았습니다.]"
            elif ext == '.xlsx':
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(file_path, data_only=True)
                    for sheet in wb.worksheets:
                        for row in sheet.iter_rows(values_only=True):
                            row_text = " ".join([str(cell) for cell in row if cell is not None])
                            if row_text.strip():
                                text += row_text + "\n"
                except ImportError:
                    text = "[오류: openpyxl 라이브러리가 설치되지 않았습니다.]"
            elif ext == '.csv':
                import csv
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f)
                        for row in reader:
                            text += " ".join(row) + "\n"
                except UnicodeDecodeError:
                    with open(file_path, 'r', encoding='euc-kr') as f:
                        reader = csv.reader(f)
                        for row in reader:
                            text += " ".join(row) + "\n"
            else:
                text = f"[지원하지 않는 확장자입니다: {ext}]"
        except Exception as e:
            text = f"[파일 읽기 오류: {str(e)}]"
            
        return text
