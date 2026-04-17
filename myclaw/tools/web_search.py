from ddgs import DDGS

from myclaw.tool_base import ToolBase, tool


@tool
class WebSearchTool(ToolBase):
    name = "web-search"

    def run(self, query: str, brief: bool, max_results: int = 10) -> str:
        """
        Search the web for realtime information. The search results may contain commercial ads, so the caller may need to do the filtering at their judgement.
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
        if brief:
            result = "\n\n".join(f"{r['title']}\n{r['href']}" for r in results)
        else:
            result = "\n\n".join(
                f"**{r['title']}**\n{r['href']}\n{r['body']}" for r in results
            )
        print(f"[WebSearchTool] Execution completed.")
        return result