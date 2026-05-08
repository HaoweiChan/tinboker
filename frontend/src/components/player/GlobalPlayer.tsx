import React from 'react';
import { usePlayerStore } from '@/store/usePlayerStore';
import { SpotifyEmbed } from '@/components/podcast/SpotifyEmbed';
import { X, ChevronDown, ChevronUp, Play, Pause, Clock, RotateCcw, RotateCw } from 'lucide-react';
import { cn } from '@/lib/utils';

export const GlobalPlayer: React.FC = () => {
    const { player, closePlayer, clearSeekRequest } = usePlayerStore();
    const [isExpanded, setIsExpanded] = React.useState(false);
    const spotifyEmbedRef = React.useRef<any>(null);
    const [, setIsEmbedReady] = React.useState(false);
    const [playbackState, setPlaybackState] = React.useState({
        position: 0,
        duration: 0,
        isPaused: true,
        isBuffering: false
    });
    const [hoveredSection, setHoveredSection] = React.useState<number | null>(null);

    // Reset state when episode changes
    React.useEffect(() => {
        setIsEmbedReady(false);
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
            const seekTarget = player.seekRequest;

            // Clear the request first to prevent duplicate processing
            clearSeekRequest();
            
            // Then execute the seek (with a tiny delay to ensure state is settled)
            setTimeout(() => {
                if (spotifyEmbedRef.current) {
                    spotifyEmbedRef.current.seekTo(seekTarget);
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

    // Handle progress bar click to seek
    const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
        e.stopPropagation();
        if (!spotifyEmbedRef.current || playbackState.duration === 0) return;

        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percentage = x / rect.width;
        const seekTime = Math.floor(percentage * playbackState.duration);

        spotifyEmbedRef.current.seekTo(seekTime);
    };

    // Handle section click to seek
    const handleSectionClick = (timestampSeconds: number) => {
        if (spotifyEmbedRef.current) {
            spotifyEmbedRef.current.seekTo(timestampSeconds);
        }
    };

    // If not visible or no data, don't render
    if (!player.isPlayerVisible || !player.currentEpisodeData) {
        return null;
    }

    const progress = playbackState.duration > 0
        ? (playbackState.position / playbackState.duration) * 100
        : 0;

    const sections = player.currentEpisodeData.timestampedSections || [];
    const currentSection = [...sections].reverse().find(s => s.timestampSeconds <= playbackState.position);

    return (
        <div className="fixed bottom-0 left-0 right-0 z-[80] shadow-[0_-8px_30px_rgba(0,0,0,0.12)]">
            <div className="bg-white/95 dark:bg-slate-900/95 border-t border-slate-200 dark:border-slate-700 backdrop-blur-md">
                <div className="max-w-7xl mx-auto w-full">

                    {/* Expanded Section List */}
                    <div className={cn(
                        "overflow-hidden transition-all duration-300 ease-in-out",
                        isExpanded ? "max-h-[300px]" : "max-h-0"
                    )}>
                        <div className="px-2 py-3 border-b border-slate-200 dark:border-slate-700 overflow-y-auto max-h-[280px] no-scrollbar">
                            <div className="flex items-center gap-2 mb-3 px-2">
                                <Clock size={14} className="text-slate-500" />
                                <span className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                                    章節
                                </span>
                            </div>

                            {sections.length > 0 ? (
                                <div className="space-y-1">
                                    {sections.map((section, index) => {
                                        const isActive = currentSection?.timestampSeconds === section.timestampSeconds;
                                        return (
                                            <button
                                                key={`${section.timestampSeconds}-${index}`}
                                                onClick={() => handleSectionClick(section.timestampSeconds)}
                                                className={cn(
                                                    "w-full flex items-start gap-3 px-3 py-2.5 rounded-lg text-left transition-all cursor-pointer group",
                                                    isActive
                                                        ? "bg-amber-100 dark:bg-amber-900/30 shadow-sm"
                                                        : "hover:bg-slate-100 dark:hover:bg-slate-800"
                                                )}
                                            >
                                                <span className={cn(
                                                    "flex-shrink-0 px-2.5 py-1 rounded text-xs font-mono tabular-nums font-medium",
                                                    isActive
                                                        ? "bg-amber-500 text-white shadow-sm"
                                                        : "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-400 group-hover:bg-amber-200 dark:group-hover:bg-amber-900/50"
                                                )}>
                                                    {section.formattedTime}
                                                </span>
                                                <div className="flex-1 min-w-0">
                                                    <span className={cn(
                                                        "block text-sm leading-relaxed",
                                                        isActive
                                                            ? "text-amber-700 dark:text-amber-300 font-semibold"
                                                            : "text-slate-700 dark:text-slate-300"
                                                    )}>
                                                        {section.title}
                                                    </span>
                                                </div>
                                                {isActive && (
                                                    <span className="flex-shrink-0 w-2 h-2 mt-1.5 rounded-full bg-amber-500 animate-pulse" />
                                                )}
                                            </button>
                                        );
                                    })}
                                </div>
                            ) : (
                                <div className="text-sm text-slate-500 dark:text-slate-400 text-center py-4">
                                    此節目無章節資訊
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Main Player Controls */}
                    <div className="px-4 py-2">
                        <div className="flex items-center gap-4">
                            {/* Playback Controls Group */}
                            <div className="flex items-center gap-1.5 flex-shrink-0">
                                {/* Rewind 15s */}
                                <button
                                    onClick={() => handleSeekRelative(-15)}
                                    className="rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-colors cursor-pointer relative flex items-center justify-center w-10 h-10"
                                    title="倒退 15 秒"
                                >
                                    <RotateCcw size={26} strokeWidth={1.2} className="opacity-70" />
                                    <span className="absolute text-[10px] font-bold">15</span>
                                </button>

                                {/* Play/Pause Button */}
                                <button
                                    onClick={handlePlayPause}
                                    className="flex-shrink-0 w-10 h-10 rounded-full bg-amber-500 hover:bg-amber-600 text-white flex items-center justify-center transition-colors cursor-pointer"
                                    title={playbackState.isPaused ? "播放" : "暫停"}
                                >
                                    {playbackState.isPaused ? <Play size={20} fill="currentColor" /> : <Pause size={20} fill="currentColor" />}
                                </button>

                                {/* Forward 15s */}
                                <button
                                    onClick={() => handleSeekRelative(15)}
                                    className="rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-colors cursor-pointer relative flex items-center justify-center w-10 h-10"
                                    title="快進 15 秒"
                                >
                                    <RotateCw size={26} strokeWidth={1.2} className="opacity-70" />
                                    <span className="absolute text-[10px] font-bold">15</span>
                                </button>
                            </div>

                            {/* Episode Info and Progress */}
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between mb-0.5">
                                    <div className="flex items-center gap-2 min-w-0 flex-1">
                                        <span className="text-sm font-bold truncate text-slate-900 dark:text-slate-100">
                                            {player.currentEpisodeData.title}
                                        </span>
                                        <span className="text-xs text-slate-500 dark:text-slate-400 truncate hidden sm:inline">
                                            • {player.currentEpisodeData.showName}
                                        </span>
                                        {currentSection && (
                                            <span className="text-xs truncate hidden md:inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                                                <span className="w-1 h-1 rounded-full bg-slate-200 dark:bg-slate-600" />
                                                ▶ {currentSection.title}
                                            </span>
                                        )}
                                    </div>

                                    {/* Right Actions: Expand, Close */}
                                    <div className="flex items-center gap-1 ml-4">
                                        {sections.length > 0 && (
                                            <button
                                                onClick={() => setIsExpanded(!isExpanded)}
                                                className={cn(
                                                    "p-1.5 rounded-full transition-colors cursor-pointer",
                                                    isExpanded
                                                        ? "bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400"
                                                        : "hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400"
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
                                            className="p-1.5 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20 dark:hover:text-red-400 rounded-full text-slate-400 dark:text-slate-500 transition-colors cursor-pointer"
                                            title="關閉"
                                        >
                                            <X size={16} />
                                        </button>
                                    </div>
                                </div>

                                {/* Progress Bar with Section Markers */}
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-mono text-slate-500 dark:text-slate-400 tabular-nums w-8 text-right">
                                        {formatTime(playbackState.position)}
                                    </span>
                                    <div
                                        onClick={handleProgressClick}
                                        className="flex-1 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full cursor-pointer group relative overflow-visible"
                                    >
                                        {/* Progress Fill */}
                                        <div
                                            className="h-full bg-amber-500 rounded-full transition-all relative z-10"
                                            style={{ width: `${progress}%` }}
                                        />

                                        {/* Section Markers */}
                                        {playbackState.duration > 0 && sections.map((section, index) => {
                                            const markerPosition = (section.timestampSeconds / playbackState.duration) * 100;
                                            const isCurrentSection = currentSection?.timestampSeconds === section.timestampSeconds;
                                            return (
                                                <div
                                                    key={`marker-${index}`}
                                                    className={cn(
                                                        "absolute top-1/2 -translate-y-1/2 z-20 transition-all cursor-pointer",
                                                        isCurrentSection
                                                            ? "w-1 h-4 bg-amber-600 dark:bg-amber-400 rounded-sm shadow-md"
                                                            : "w-[3px] h-3 bg-slate-400/90 dark:bg-slate-500/90 hover:bg-amber-500 hover:h-4 hover:w-1 hover:shadow-lg"
                                                    )}
                                                    style={{ left: `${markerPosition}%`, marginLeft: '-2px' }}
                                                    onMouseEnter={() => setHoveredSection(index)}
                                                    onMouseLeave={() => setHoveredSection(null)}
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleSectionClick(section.timestampSeconds);
                                                    }}
                                                >
                                                    {hoveredSection === index && (
                                                        <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 text-[11px] px-3 py-1.5 rounded-md shadow-xl whitespace-nowrap pointer-events-none z-50 animate-in fade-in slide-in-from-bottom-1 duration-150 max-w-[200px] truncate font-medium">
                                                            {section.title}
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}

                                        {/* Hover overlay */}
                                        <div className="absolute inset-0 bg-amber-400/20 opacity-0 group-hover:opacity-100 transition-opacity rounded-full" />
                                    </div>
                                    <span className="text-[10px] font-mono text-slate-500 dark:text-slate-400 tabular-nums w-8">
                                        {formatTime(playbackState.duration)}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Hidden Spotify Embed (audio only) */}
                    <div className="h-0 overflow-hidden">
                        {player.currentEpisodeData.spotifyUri && (
                            <SpotifyEmbed
                                key={player.currentEpisodeData.spotifyUri}
                                uri={player.currentEpisodeData.spotifyUri}
                                height={0}
                                ref={spotifyEmbedRef}
                                onPlayerReady={() => setIsEmbedReady(true)}
                                onPlaybackUpdate={handlePlaybackUpdate}
                            />
                        )}
                    </div>

                </div>
            </div>
        </div>
    );
};
