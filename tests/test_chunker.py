from ingestion.document_loader import PageData
from chunking.semantic_chunker import chunk_pages
from config import CHUNK_SIZE

def test_chunking_empty_input():
    chunks = chunk_pages([])
    assert len(chunks) == 0

def test_chunking_text():
    # Simulate a single page with enough text to create multiple chunks
    text = "Word " * 500  # 2500 characters
    page = PageData(page_num=1, text=text, source="test.txt")
    
    chunks = chunk_pages([page])
    
    assert len(chunks) > 0
    # The first chunk should be roughly CHUNK_SIZE but bounded by word boundaries
    assert len(chunks[0].text) <= CHUNK_SIZE + 50
    assert chunks[0].source == "test.txt"
    assert chunks[0].chunk_type == "text"

def test_chunking_table():
    page = PageData(page_num=1, text="Before table", source="test.pdf")
    page.tables = [
        [["Header 1", "Header 2"], ["Row 1", "Row 2"]]
    ]
    
    chunks = chunk_pages([page])
    
    # We should get 1 text chunk and 1 table chunk
    assert len(chunks) == 2
    types = {c.chunk_type for c in chunks}
    assert "text" in types
    assert "table" in types
    
    table_chunk = next(c for c in chunks if c.chunk_type == "table")
    assert "Header 1" in table_chunk.text
    assert "Row 2" in table_chunk.text
