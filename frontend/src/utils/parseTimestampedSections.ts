import { formatTimeFromMs, formatTimeFromSeconds } from './timeFormat';

export interface TimestampedSection {
    title: string;
    timestampSeconds: number;
    formattedTime: string;
}

interface SummaryHeading {
    title: string;
    milliseconds: number | null;
}

const MIN_PLAUSIBLE_TOPIC_MARKER_MS = 1000;

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

/**
 * Build player chapters from summary headings.
 *
 * Newer summaries should carry real `#time:milliseconds` markers on section
 * headings. Some existing production episodes have no markers, while others
 * have ordinal-looking markers (`#time:1`, `#time:2`) that collapse to 00:00.
 * For those cases, keep the user-facing chapter titles from the summary and
 * place them across the transcript duration instead of falling back to raw
 * transcript snippets.
 */
export function parseSummaryTopicSections(summaryMarkdown: string, transcriptMarkdown?: string | null): TimestampedSection[] {
    const headings = parseSummaryHeadings(summaryMarkdown);
    if (headings.length === 0) return [];

    const timeline = transcriptMarkdown ? parseTranscriptTimeline(transcriptMarkdown) : [];
    const durationSeconds = timeline.length > 0 ? Math.max(...timeline.map((item) => item.timestampSeconds)) : 0;

    const explicitSections = headings
        .map((heading) => {
            if (!isPlausibleTopicMarker(heading.milliseconds, durationSeconds)) return null;
            return sectionFromSeconds(heading.title, Math.floor((heading.milliseconds || 0) / 1000));
        })
        .filter((section): section is TimestampedSection => section !== null);

    if (explicitSections.length === headings.length && hasUsefulTimeline(explicitSections)) {
        return dedupeAndSort(explicitSections);
    }

    if (durationSeconds <= 0) return dedupeAndSort(explicitSections);

    const synthesized = headings.map((heading, index) => {
        const seconds = synthesizedTopicTime(index, headings.length, durationSeconds);
        return sectionFromSeconds(heading.title, seconds);
    });

    return dedupeAndSort(synthesized);
}

function parseSummaryHeadings(markdown: string): SummaryHeading[] {
    const headings: SummaryHeading[] = [];
    const pattern = /^#{2,4}\s+(.+?)(?:\s*\(#time:\s*(\d+)\))?\s*$/gm;
    let match;

    while ((match = pattern.exec(markdown)) !== null) {
        const title = cleanTitle(match[1]);
        if (!title) continue;
        headings.push({
            title,
            milliseconds: match[2] ? parseInt(match[2], 10) : null,
        });
    }

    return headings;
}

function parseTranscriptTimeline(markdown: string): TimestampedSection[] {
    return parseTimestampedSections(markdown).filter((section) => section.timestampSeconds >= 0);
}

function cleanTitle(title: string): string {
    return title
        .replace(/\s*\(#time:\s*\d+\)/g, '')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/[*_`>~]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
}

function isPlausibleTopicMarker(milliseconds: number | null, durationSeconds: number): boolean {
    if (milliseconds == null || !Number.isFinite(milliseconds)) return false;
    if (milliseconds < MIN_PLAUSIBLE_TOPIC_MARKER_MS) return false;
    if (durationSeconds <= 0) return true;
    return milliseconds / 1000 <= durationSeconds + 60;
}

function hasUsefulTimeline(sections: TimestampedSection[]): boolean {
    const uniqueTimes = new Set(sections.map((section) => section.timestampSeconds));
    if (uniqueTimes.size < sections.length) return false;
    return sections.some((section) => section.timestampSeconds > 0);
}

function synthesizedTopicTime(index: number, total: number, durationSeconds: number): number {
    if (total <= 1) return 0;
    const usableDuration = Math.max(0, durationSeconds * 0.92);
    return Math.floor((usableDuration * index) / total);
}

function sectionFromSeconds(title: string, timestampSeconds: number): TimestampedSection {
    return {
        title,
        timestampSeconds,
        formattedTime: formatTimeFromSeconds(timestampSeconds),
    };
}

function dedupeAndSort(sections: TimestampedSection[]): TimestampedSection[] {
    const seen = new Set<string>();
    const result: TimestampedSection[] = [];

    for (const section of sections) {
        const key = `${section.timestampSeconds}:${section.title}`;
        if (seen.has(key)) continue;
        seen.add(key);
        result.push(section);
    }

    return result.sort((a, b) => a.timestampSeconds - b.timestampSeconds);
}
