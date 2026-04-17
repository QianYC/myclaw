"""Web search tool backed by DuckDuckGo via the ddgs package."""

from ddgs import DDGS

from myclaw.tool_base import ToolBase, tool


@tool
class WebSearchTool(ToolBase):
    """Search the web and return formatted title/URL/snippet results."""

    name = "web-search"

    # pylint: disable=arguments-differ
    def run(self, query: str, brief: bool, max_results: int = 10) -> str:
        """
        Search the web for realtime information. The search results may contain
        commercial ads, so the caller may need to do the filtering at their judgement.
        Args:
            query: The search query string.
            brief: Whether to return brief results.
            max_results: Maximum number of results to return (default: 10).
        Returns:
            Formatted search results with title, URL, and snippet.
        """
        print(f"[WebSearchTool] Searching for: {query} (brief={brief}, max_results={max_results})")
        results = DDGS().text(query, max_results=max_results)
        if not results:
            result = "No results found."
        elif brief:
            result = "\n\n".join(f"{r['title']}\n{r['href']}" for r in results)
        else:
            result = "\n\n".join(
                f"**{r['title']}**\n{r['href']}\n{r['body']}" for r in results
            )
        print("[WebSearchTool] Execution completed.")
        return result
