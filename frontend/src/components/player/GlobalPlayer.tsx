import React from 'react';
import { usePlayerStore } from '@/store/usePlayerStore';
import { SpotifyEmbed, type SpotifyEmbedRef } from '@/components/podcast/SpotifyEmbed';
import { X, ChevronDown, ChevronUp, Play, Pause, Clock, RotateCcw, RotateCw, SkipForward, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';

export const GlobalPlayer: React.FC = () => {
    const { player, closePlayer, clearSeekRequest } = usePlayerStore();
    const [isExpanded, setIsExpanded] = React.useState(false);
    // A drag on the progress bar. The seek fires once on release, not per move.
    const [scrub, setScrub] = React.useState<{ sec: number; lastX: number; rate: number } | null>(null);
    const spotifyEmbedRef = React.useRef<SpotifyEmbedRef | null>(null);
    const [, setIsEmbedReady] = React.useState(false);
    const [playbackState, setPlaybackState] = React.useState({
        position: 0,
        duration: 0,
        isPaused: true,
        isBuffering: false
    });
    const [hoveredSection, setHoveredSection] = React.useState<number | null>(null);
    // Last timestamp we were asked to jump to. A visitor not signed in to Spotify gets a
    // short preview from the embed (duration ~60s), so a chapter past it can't be reached
    // in-page; the player then offers the same moment in Spotify itself (?t=seconds).
    const [seekTarget, setSeekTarget] = React.useState<number | null>(null);

    // Reset state when episode changes
    React.useEffect(() => {
        setIsEmbedReady(false);
        setSeekTarget(null);
        setPlaybackState({ position: 0, duration: 0, isPaused: true, isBuffering: false });
    }, [player.currentEpisodeData?.id]);

    // Handle playback update from Spotify
    const handlePlaybackUpdate = React.useCallback((state: {
        position: number;
        duration: number;
        isPaused: boolean;
        isBuffering: boolean;
    }) => {
        setPlaybackState(state);
    }, []);

    // Handle seek requests from store
    React.useEffect(() => {
        if (player.seekRequest !== null && spotifyEmbedRef.current) {
            const target = player.seekRequest;
            setSeekTarget(target);

            // Clear the request first to prevent duplicate processing
            clearSeekRequest();

            // Then execute the seek (with a tiny delay to ensure state is settled)
            setTimeout(() => {
                if (spotifyEmbedRef.current) {
                    spotifyEmbedRef.current.seekTo(target);
                }
            }, 50);
        }
    }, [player.seekRequest, clearSeekRequest]);

    // Format seconds to MM:SS
    const formatTime = (seconds: number): string => {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    // Handle play/pause toggle
    const handlePlayPause = (e: React.MouseEvent) => {
        e.stopPropagation();
        if (spotifyEmbedRef.current) {
            spotifyEmbedRef.current.togglePlay();
        }
    };

    // Handle relative seek (fast forward / rewind)
    const handleSeekRelative = (seconds: number) => {
        if (spotifyEmbedRef.current) {
            const newPosition = Math.max(0, Math.min(playbackState.position + seconds, playbackState.duration));
            spotifyEmbedRef.current.seekTo(newPosition);
        }
    };

    // Progress bar scrubbing. Dragging straight along the bar maps the finger to the
    // timeline; sliding the finger up and away slows it down (½ past 40px, ¼ past
    // 100px), the iOS fine-scrub gesture, so a thumb on a 375px bar can still land on
    // a sentence rather than a 10-second jump.
    const secAt = (clientX: number, rect: DOMRect) =>
        Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * playbackState.duration;

    const handleScrubStart = (e: React.PointerEvent<HTMLDivElement>) => {
        e.stopPropagation();
        if (!spotifyEmbedRef.current || playbackState.duration === 0) return;
        e.currentTarget.setPointerCapture(e.pointerId);
        const rect = e.currentTarget.getBoundingClientRect();
        setScrub({ sec: secAt(e.clientX, rect), lastX: e.clientX, rate: 1 });
    };

    const handleScrubMove = (e: React.PointerEvent<HTMLDivElement>) => {
        if (!scrub) return;
        const rect = e.currentTarget.getBoundingClientRect();
        const above = rect.top - e.clientY;
        const rate = above > 100 ? 0.25 : above > 40 ? 0.5 : 1;
        const sec = rate === 1
            ? secAt(e.clientX, rect)
            : Math.max(0, Math.min(playbackState.duration,
                scrub.sec + ((e.clientX - scrub.lastX) / rect.width) * playbackState.duration * rate));
        setScrub({ sec, lastX: e.clientX, rate });
    };

    const handleScrubEnd = () => {
        if (!scrub) return;
        spotifyEmbedRef.current?.seekTo(Math.floor(scrub.sec));
        setPlaybackState((s) => ({ ...s, position: Math.floor(scrub.sec) }));
        setScrub(null);
    };

    // Handle section click to seek
    const handleSectionClick = (timestampSeconds: number) => {
        setSeekTarget(timestampSeconds);
        if (spotifyEmbedRef.current) {
            spotifyEmbedRef.current.seekTo(timestampSeconds);
        }
    };

    // If not visible or no data, don't render
    if (!player.isPlayerVisible || !player.currentEpisodeData) {
        return null;
    }

    const shownPosition = scrub ? scrub.sec : playbackState.position;
    const progress = playbackState.duration > 0
        ? (shownPosition / playbackState.duration) * 100
        : 0;

    const spotifyEpisodeId = player.currentEpisodeData.spotifyUri?.split(':').pop();
    const unreachableSeek = spotifyEpisodeId && seekTarget !== null && playbackState.duration > 0 && seekTarget > playbackState.duration
        ? seekTarget
        : null;

    const sections = player.currentEpisodeData.timestampedSections || [];
    // Only real chapters track "current"; skip chips never become the active section.
    const currentSection = [...sections].reverse().find(s => !s.skippable && s.timestampSeconds <= playbackState.position);
    const scrubSection = scrub ? [...sections].reverse().find(s => !s.skippable && s.timestampSeconds <= scrub.sec) : undefined;
    const activeSkippableSection = sections.find(
        (s) => s.skippable && playbackState.position >= s.timestampSeconds && playbackState.position < (s.endSeconds || s.timestampSeconds)
    );

    // One track, two placements: inline beside the times from sm up, and on a phone a
    // full-width strip along the player's top edge — inline it was squeezed to ~110px
    // between the three buttons and the title row.
    const renderTrack = (sizing: string) => (
            <div
                onPointerDown={handleScrubStart}
                onPointerMove={handleScrubMove}
                onPointerUp={handleScrubEnd}
                onPointerCancel={() => setScrub(null)}
                onClick={(e) => e.stopPropagation()}
                className={cn("bg-muted rounded-full cursor-pointer group relative overflow-visible touch-none select-none", sizing)}
            >
                <div
                    className={cn("h-full bg-accent-info rounded-full relative z-10", !scrub && "transition-all")}
                    style={{ width: `${progress}%` }}
                />
                {scrub && (
                    <div
                        className="absolute bottom-full mb-3 -translate-x-1/2 z-50 pointer-events-none px-2.5 py-1.5 rounded-md bg-foreground text-background shadow-xl text-center whitespace-nowrap"
                        style={{ left: `clamp(48px, ${progress}%, calc(100% - 48px))` }}
                    >
                        <div className="font-mono tabular-nums text-sm font-semibold">{formatTime(scrub.sec)}</div>
                        {scrubSection && <div className="text-2xs max-w-[200px] truncate opacity-80">{scrubSection.title}</div>}
                        {scrub.rate < 1 && <div className="text-2xs opacity-70">{scrub.rate === 0.5 ? '半速微調' : '¼ 速微調'}</div>}
                    </div>
                )}
                {scrub && (
                    <div
                        className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 z-30 w-3.5 h-3.5 rounded-full bg-accent-info ring-2 ring-background pointer-events-none"
                        style={{ left: `${progress}%` }}
                    />
                )}
                {playbackState.duration > 0 && sections.map((section, index) => {
                    const skippable = !!section.skippable;
                    const markerPosition = (section.timestampSeconds / playbackState.duration) * 100;
                    const isCurrentSection = !skippable && currentSection?.timestampSeconds === section.timestampSeconds;
                    return (
                        <div
                            key={`marker-${index}`}
                            className={cn(
                                "absolute top-1/2 -translate-y-1/2 z-20 transition-all cursor-pointer",
                                isCurrentSection
                                    ? "w-1 h-4 bg-accent-info rounded-sm shadow-md"
                                    : "w-[3px] h-3 bg-muted-foreground/50 hover:bg-accent-info hover:h-4 hover:w-1 hover:shadow-lg"
                            )}
                            style={{ left: `${markerPosition}%`, marginLeft: '-2px' }}
                            onPointerDown={(e) => e.stopPropagation()}
                            onMouseEnter={() => setHoveredSection(index)}
                            onMouseLeave={() => setHoveredSection(null)}
                            onClick={(e) => {
                                e.stopPropagation();
                                handleSectionClick(section.timestampSeconds);
                            }}
                        >
                            {hoveredSection === index && (
                                <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 bg-foreground text-background text-2xs px-3 py-1.5 rounded-md shadow-xl whitespace-nowrap pointer-events-none z-50 animate-in fade-in slide-in-from-bottom-1 duration-150 max-w-[200px] truncate font-medium">
                                    {section.title}
                                </div>
                            )}
                        </div>
                    );
                })}
                <div className="absolute inset-0 bg-accent-info/20 opacity-0 group-hover:opacity-100 transition-opacity rounded-full" />
            </div>
    );

    return (
        <div className="fixed left-0 right-0 bottom-14 lg:bottom-0 z-[80] shadow-[0_-8px_30px_rgba(0,0,0,0.35)]">
            <div className="bg-card/95 border-t border-border backdrop-blur-md">
                <div className="max-w-7xl mx-auto w-full">

                    {/* Expanded Section List (full chapter panel) */}
                    <div className={cn(
                        "overflow-hidden transition-all duration-300 ease-in-out",
                        isExpanded ? "max-h-[300px]" : "max-h-0"
                    )}>
                        <div className="px-2 py-3 border-b border-border overflow-y-auto max-h-[280px] no-scrollbar">
                            <div className="flex items-center gap-2 mb-3 px-2">
                                <Clock size={14} className="text-muted-foreground" />
                                <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-[0.08em]">
                                    章節
                                </span>
                            </div>

                            {sections.length > 0 ? (
                                <div className="space-y-1">
                                    {sections.map((section, index) => {
                                        // Skippable segment: clicking jumps PAST it (to its end), and the
                                        // row reads muted with a skip icon so a listener can bypass a
                                        // sponsor read / life-story tangent without it being a "chapter".
                                        const skippable = !!section.skippable;
                                        const isActive = !skippable && currentSection?.timestampSeconds === section.timestampSeconds;
                                        return (
                                            <button
                                                key={`${section.timestampSeconds}-${index}`}
                                                onClick={() => handleSectionClick(section.timestampSeconds)}
                                                className={cn(
                                                    "w-full flex items-start gap-3 px-3 py-2.5 rounded-md text-left transition-colors cursor-pointer group",
                                                    isActive
                                                        ? "bg-accent-info-soft"
                                                        : "hover:bg-muted"
                                                )}
                                            >
                                                <span className={cn(
                                                    "flex-shrink-0 px-2 py-0.5 rounded text-xs font-mono tabular-nums font-medium inline-flex items-center gap-1",
                                                    isActive
                                                        ? "bg-accent-info text-white"
                                                        : "bg-muted text-muted-foreground group-hover:bg-accent-info-soft group-hover:text-accent-info"
                                                )}>
                                                    {section.formattedTime}
                                                </span>
                                                <div className="flex-1 min-w-0">
                                                    <span className={cn(
                                                        "block text-sm leading-relaxed",
                                                        isActive
                                                            ? "text-accent-info font-semibold"
                                                            : "text-foreground/80"
                                                    )}>
                                                        {section.title}
                                                    </span>
                                                </div>
                                                {isActive && (
                                                    <span className="flex-shrink-0 w-2 h-2 mt-1.5 rounded-full bg-accent-info animate-pulse" />
                                                )}
                                            </button>
                                        );
                                    })}
                                </div>
                            ) : (
                                <div className="text-sm text-muted-foreground text-center py-4">
                                    此節目無章節資訊
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Phone: progress as a full-width strip; the pseudo-element widens the tap target */}
                    <div className="sm:hidden">
                        {renderTrack("h-1 rounded-none before:absolute before:inset-x-0 before:-top-1 before:-bottom-3 before:content-['']")}
                    </div>

                    {/* Main Player Controls */}
                    <div className="px-4 py-2">
                        <div className="flex items-center gap-3 sm:gap-4">
                            {/* Playback Controls Group */}
                            <div className="flex items-center gap-1.5 flex-shrink-0">
                                <button
                                    onClick={() => handleSeekRelative(-15)}
                                    className="rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer relative flex items-center justify-center w-10 h-10"
                                    title="倒退 15 秒"
                                >
                                    <RotateCcw size={30} strokeWidth={1.6} />
                                    <span className="absolute pt-px text-[9px] font-semibold tabular-nums leading-none">15</span>
                                </button>
                                <button
                                    onClick={handlePlayPause}
                                    className="flex-shrink-0 w-11 h-11 rounded-full bg-foreground text-background hover:opacity-90 flex items-center justify-center transition-opacity cursor-pointer"
                                    title={playbackState.isPaused ? "播放" : "暫停"}
                                >
                                    {playbackState.isPaused ? <Play size={18} fill="currentColor" className="ml-0.5" /> : <Pause size={18} fill="currentColor" />}
                                </button>
                                <button
                                    onClick={() => handleSeekRelative(15)}
                                    className="rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer relative flex items-center justify-center w-10 h-10"
                                    title="快進 15 秒"
                                >
                                    <RotateCw size={30} strokeWidth={1.6} />
                                    <span className="absolute pt-px text-[9px] font-semibold tabular-nums leading-none">15</span>
                                </button>
                            </div>

                            {/* Episode Info and Progress */}
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between sm:mb-1">
                                    <div className="flex items-center gap-2 min-w-0 flex-1">
                                        <span className="text-sm font-semibold truncate text-foreground">
                                            {player.currentEpisodeData.title}
                                        </span>
                                        <span className="text-xs text-muted-foreground truncate hidden sm:inline">
                                            · {player.currentEpisodeData.showName}
                                        </span>
                                        {currentSection && (
                                            <span className="text-xs truncate hidden md:inline-flex items-center gap-1.5 text-accent-info">
                                                <span className="w-1 h-1 rounded-full bg-muted-foreground/50" />
                                                {currentSection.title}
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-1 ml-2 sm:ml-4">
                                        {unreachableSeek !== null && (
                                            <a
                                                href={`https://open.spotify.com/episode/${spotifyEpisodeId}?t=${unreachableSeek}`}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                onClick={(e) => e.stopPropagation()}
                                                className="mr-1 hidden sm:inline-flex shrink-0 items-center gap-1.5 px-3 py-1.5 rounded-lg bg-foreground text-background text-xs font-semibold shadow hover:opacity-90 transition-opacity animate-in fade-in slide-in-from-right duration-200"
                                                title="此處只能試聽，登入 Spotify 可在頁面內收聽完整集數"
                                            >
                                                在 Spotify 從 {formatTime(unreachableSeek)} 收聽
                                                <ExternalLink size={12} />
                                            </a>
                                        )}
                                        {activeSkippableSection && (
                                            <button
                                                onClick={() => handleSectionClick(activeSkippableSection.endSeconds || activeSkippableSection.timestampSeconds)}
                                                className="mr-1 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent-info hover:bg-accent-info/90 text-white text-xs font-semibold shadow transition-all cursor-pointer animate-in fade-in slide-in-from-right duration-200"
                                                title={`略過 ${activeSkippableSection.title}`}
                                            >
                                                <span>略過 {activeSkippableSection.title}</span>
                                                <SkipForward size={12} className="fill-current text-white" />
                                            </button>
                                        )}
                                        {sections.length > 0 && (
                                            <button
                                                onClick={() => setIsExpanded(!isExpanded)}
                                                className={cn(
                                                    "p-1.5 rounded-full transition-colors cursor-pointer",
                                                    isExpanded
                                                        ? "bg-accent-info-soft text-accent-info"
                                                        : "hover:bg-muted text-muted-foreground hover:text-foreground"
                                                )}
                                                title={isExpanded ? "收起章節" : "展開章節"}
                                            >
                                                {isExpanded ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
                                            </button>
                                        )}
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                closePlayer();
                                            }}
                                            className="p-1.5 hover:bg-muted text-muted-foreground hover:text-foreground rounded-full transition-colors cursor-pointer"
                                            title="關閉"
                                        >
                                            <X size={16} />
                                        </button>
                                    </div>
                                </div>

                                {/* Phone second line: the time, and the Spotify fallback as a text link —
                                    as a button in the title row it pushed ✕ off a 375px screen. */}
                                <div className="sm:hidden flex items-center gap-2 min-w-0 text-2xs text-muted-foreground">
                                    <span className="font-mono tabular-nums whitespace-nowrap shrink-0">
                                        {formatTime(playbackState.position)} / {formatTime(playbackState.duration)}
                                    </span>
                                    {unreachableSeek !== null && (
                                        <a
                                            href={`https://open.spotify.com/episode/${spotifyEpisodeId}?t=${unreachableSeek}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="inline-flex min-w-0 items-center gap-1 font-semibold text-foreground underline underline-offset-2 truncate"
                                        >
                                            在 Spotify 從 {formatTime(unreachableSeek)} 收聽
                                            <ExternalLink size={10} />
                                        </a>
                                    )}
                                </div>

                                {/* Progress Bar with Section Markers */}
                                <div className="hidden sm:flex items-center gap-2">
                                    <span className="text-2xs font-mono text-muted-foreground tabular-nums w-9 text-right">
                                        {formatTime(playbackState.position)}
                                    </span>
                                    {renderTrack('flex-1 h-1.5')}
                                    <span className="text-2xs font-mono text-muted-foreground tabular-nums w-9">
                                        {formatTime(playbackState.duration)}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Hidden playback engine */}
                    <div className="h-0 overflow-hidden" aria-hidden="true">
                        {player.currentEpisodeData.spotifyUri ? (
                            <SpotifyEmbed
                                key={player.currentEpisodeData.spotifyUri}
                                uri={player.currentEpisodeData.spotifyUri}
                                height={152}
                                ref={spotifyEmbedRef}
                                onPlayerReady={() => setIsEmbedReady(true)}
                                onPlaybackUpdate={handlePlaybackUpdate}
                            />
                        ) : null}
                    </div>

                </div>
            </div>
        </div>
    );
};
