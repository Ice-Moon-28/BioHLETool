WEB_TOOLS = """
[
{
  "name": "fetch_supplementary_info_from_doi",
  "description": "Fetch supplementary information for a paper given its DOI and return a research log and downloaded file paths.",
  "parameters": {
    "type": "object",
    "properties": {
      "doi": {
        "type": "string",
        "description": "The paper DOI."
      },
      "output_dir": {
        "type": "string",
        "description": "Directory to save supplementary files.",
        "default": "supplementary_info"
      }
    },
    "required": ["doi"]
  }
},
{
  "name": "query_arxiv",
  "description": "Query arXiv for papers based on a search query.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The search query string."
      },
      "max_papers": {
        "type": "integer",
        "description": "The maximum number of papers to retrieve.",
        "default": 10
      }
    },
    "required": ["query"]
  }
},
{
  "name": "query_scholar",
  "description": "Query Google Scholar for papers based on the provided search query.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The search query string."
      }
    },
    "required": ["query"]
  }
},
{
  "name": "search_google",
  "description": "Perform a Google search and return search results with titles and URLs.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "The search query string."
      },
      "num_results": {
        "type": "integer",
        "description": "Number of results to return.",
        "default": 3
      },
      "language": {
        "type": "string",
        "description": "Language code for search results.",
        "default": "en"
      }
    },
    "required": ["query"]
  }
},
{
  "name": "browse_webpage",
  "description": "To find details in a url, use it to browse webpage and return all textual content.",
  "parameters": {
    "type": "object",
    "properties": {
      "url": {
        "type": "string",
        "description": "The webpage URL to browse."
      }
    },
    "required": ["url"]
  }
},
{
  "name": "extract_pdf_content",
  "description": "Extract the text content of a PDF file given its URL.",
  "parameters": {
    "type": "object",
    "properties": {
      "url": {
        "type": "string",
        "description": "The URL of the PDF file to extract text from."
      }
    },
    "required": ["url"]
  }
}
]
"""