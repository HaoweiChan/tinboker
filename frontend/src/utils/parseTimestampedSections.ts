import { formatTimeFromMs } from './timeFormat';

export interface TimestampedSection {
    title: string;
    timestampSeconds: number;
    formattedTime: string;
}

/**
 * A `#time:` marker is a real audio offset only when it is 0 (episode start) or
 * at least 1000 ms. The 1–999 ms band is rejected because legacy summaries stored
 * section ORDINALS there (`#time:1`, `#time:2` …) — a writer-LLM bug now fixed in
 * the pipeline — which otherwise render as a cluster of 00:00 chapters. Genuine
 * chapter offsets are either 0 or seconds-to-minutes in, never 1–999 ms.
 */
export function isRealTimeMarker(milliseconds: number): boolean {
    return Number.isFinite(milliseconds) && (milliseconds === 0 || milliseconds >= 1000);
}

/**
 * Parse markdown to extract section headers with timestamps
 * Looks for patterns like:
 * - "## Section Title (#time:12345)"
 * - "### Section Title (#time:12345)"
 * - "**Section Title** (#time:12345)"
 * 
 * @param markdown The markdown content to parse
 * @returns Array of timestamped sections
 */
export function parseTimestampedSections(markdown: string): TimestampedSection[] {
    const sections: TimestampedSection[] = [];

    // Match patterns:
    // 1. Markdown headers: ## Title (#time:123456)
    // 2. Bold text: **Title** (#time:123456)
    // The title can be before or on the same line as the timestamp
    const patterns = [
        // Header with timestamp on same line
        /^#{1,4}\s+(.+?)\s*\(#time:\s*(\d+)\)/gm,
        // Bold text with timestamp
        /\*\*(.+?)\*\*\s*\(#time:\s*(\d+)\)/g,
        // Any line ending with timestamp, capture preceding text
        /^([^#\n][^\n]+?)\s*\(#time:\s*(\d+)\)/gm,
    ];

    for (const pattern of patterns) {
        let match;
        while ((match = pattern.exec(markdown)) !== null) {
            const title = match[1].trim()
                .replace(/^#+\s*/, '') // Remove leading hashes
                .replace(/\*\*/g, '')  // Remove bold markers
                .replace(/^\*\s*/, '') // Remove list markers
                .trim();

            if (title && title.length > 0) {
                const milliseconds = parseInt(match[2], 10);
                if (!isRealTimeMarker(milliseconds)) continue;
                const timestampSeconds = Math.floor(milliseconds / 1000);

                // Avoid duplicates
                const exists = sections.some(s => s.timestampSeconds === timestampSeconds && s.title === title);
                if (!exists) {
                    sections.push({
                        title,
                        timestampSeconds,
                        formattedTime: formatTimeFromMs(milliseconds)
                    });
                }
            }
        }
    }

    // Sort by timestamp
    sections.sort((a, b) => a.timestampSeconds - b.timestampSeconds);

    return sections;
}
