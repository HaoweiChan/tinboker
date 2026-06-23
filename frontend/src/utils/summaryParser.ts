
// The agents pipeline emits inline tag/ticker markers padded with ASCII spaces,
// e.g. "對 [經濟衰退](#tag:x) 的" — natural in markdown, but those spaces read as
// odd gaps in CJK prose. Strip a space sitting between a CJK char and a
// CJK-labelled marker (either side). Spaces around Latin labels (AI, SpaceX, HBM)
// are left alone on purpose — that CJK↔Latin gap is correct typography.
const CJK = '\\u4e00-\\u9fff\\u3000-\\u303f\\uff00-\\uffef';
const LEADING = new RegExp(`([${CJK}])[ \\t]+(\\[[${CJK}])`, 'g');
const TRAILING = new RegExp(`([${CJK}]\\]\\([^)]*\\))[ \\t]+([${CJK}])`, 'g');

export function normalizeCjkMarkerSpacing(text: string): string {
  if (!text) return text;
  return text.replace(LEADING, '$1$2').replace(TRAILING, '$1$2');
}

/**
 * Interface for parsed summary points
 */
export interface ParsedSummaryPoint {
  originalText: string;
  heading: string;
  detail: string;
  isBoldHeading: boolean;
}

/**
 * Parses markdown summary text to extract structured topics/headings.
 * 
 * Logic:
 * 1. Takes raw text (e.g., "* **Topic Name**: Detail..." or "* Topic Name")
 * 2. Extracts the "Heading" (the bold part or first phrase)
 * 3. Extracts the "Detail" (the rest of the text)
 */
export function parseSummaryTopics(summaryPoints: { text: string }[]): ParsedSummaryPoint[] {
  return summaryPoints.map(point => {
    const text = point.text.trim();
    let heading = '';
    let detail = '';
    let isBoldHeading = false;

    // Regex to match bold text at start: **Heading**: Detail or **Heading** Detail
    // Also handles cases with leading bullet points if passed raw string, 
    // but here we assume 'text' is already stripped of the list bullet from the data source if structured,
    // though the mock data usually just has the content.
    
    // Check for bold syntax: **Text**
    const boldMatch = text.match(/^\*\*([^*]+)\*\*(?::| -)?\s*(.*)/);
    
    if (boldMatch) {
      heading = boldMatch[1].trim();
      detail = boldMatch[2].trim();
      isBoldHeading = true;
    } else {
      // If no bold syntax, try to split by colon or dash if it looks like a header
      // e.g. "Topic Name: Detail..."
      const splitMatch = text.match(/^([^：:]{2,30})[：:]\s*(.*)/);
      
      if (splitMatch) {
        heading = splitMatch[1].trim();
        detail = splitMatch[2].trim();
      } else {
        // Fallback: If just a sentence, treat first ~20 chars or first comma as fake heading if long,
        // or just put everything in heading if short.
        // For this requirement, let's treat the whole text as "Heading" if it's short,
        // otherwise try to find a sentence break.
        if (text.length < 50) {
            heading = text;
        } else {
            // No clear structure, use whole text as detail, empty heading? 
            // Or extract first phrase. Let's try first phrase.
            const firstPunc = text.search(/[，,。.]/);
            if (firstPunc > 5 && firstPunc < 30) {
                heading = text.substring(0, firstPunc);
                detail = text.substring(firstPunc + 1).trim();
            } else {
               // Fallback
               heading = text; // Display full text as item
            }
        }
      }
    }

    return {
      originalText: text,
      heading,
      detail,
      isBoldHeading
    };
  });
}


