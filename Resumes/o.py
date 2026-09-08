from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("John_Smith_Two_Column_Resume.pdf")

print(result.document.export_to_markdown())