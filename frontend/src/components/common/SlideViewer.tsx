import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { ChevronLeft, ChevronRight, X, Maximize2 } from 'lucide-react';
import { parseMarpFrontmatter, parseMarpSize, renderMarpToHTML, splitMarpSlides } from '@/utils/marpParser';
import { PostProcessedSlide } from '@/utils/marpPostProcessor';

interface SlideViewerProps {
    content: string;
    className?: string;
    isDark?: boolean;
    onTickerClick?: (symbol: string) => void;
    onTagClick?: (tag: string) => void;
    episodeId?: string;
    episodeTitle?: string;
    episodeSource?: string;
    spotifyUri?: string;
    timestampedSections?: any[];
}

const SlideScaler: React.FC<{ children: React.ReactNode; width: number; height: number }> = ({ children, width, height }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const [scale, setScale] = useState(1);

    useEffect(() => {
        const updateScale = () => {
            if (!containerRef.current) return;
            const parent = containerRef.current.parentElement;
            if (!parent) return;
            const scaleW = parent.clientWidth / width;
            const scaleH = parent.clientHeight / height;
            setScale(Math.min(scaleW, scaleH));
        };
        updateScale();
        window.addEventListener('resize', updateScale);
        return () => window.removeEventListener('resize', updateScale);
    }, [width, height]);

    return (
        <div ref={containerRef} style={{
            width,
            height,
            transform: `scale(${scale})`,
            transformOrigin: 'center center'
        }}>
            {children}
        </div>
    );
};

export const SlideViewer: React.FC<SlideViewerProps> = ({
    content,
    className,
    onTickerClick,
    onTagClick,
    episodeId,
    episodeTitle,
    episodeSource,
    spotifyUri,
    timestampedSections,
}) => {
    const [selectedSlideIndex, setSelectedSlideIndex] = useState<number | null>(null);
    const [renderedSlides, setRenderedSlides] = useState<{ html: string; css: string; index: number }[]>([]);
    const [isDragging, setIsDragging] = useState(false);
    const [startX, setStartX] = useState(0);
    const [scrollLeft, setScrollLeft] = useState(0);
    const [hasDragged, setHasDragged] = useState(false);
    const scrollContainerRef = useRef<HTMLDivElement>(null);

    const metadata = useMemo(() => parseMarpFrontmatter(content), [content]);
    const slideSize = useMemo(() => parseMarpSize(metadata.size), [metadata.size]);
    const slides = useMemo(() => splitMarpSlides(content), [content]);

    useEffect(() => {
        let cancelled = false;
        const renderAll = async () => {
            const frontmatter = content.match(/^---\n([\s\S]*?)\n---\n/)?.[0] || '';
            const results = await Promise.all(
                slides.map(async (slide, index) => {
                    const fullSlideContent = frontmatter + '\n\n' + slide;
                    const { html, css } = await renderMarpToHTML(fullSlideContent);
                    return { html, css, index };
                }),
            );
            if (!cancelled) setRenderedSlides(results);
        };
        if (slides.length > 0) renderAll();
        return () => { cancelled = true; };
    }, [slides, content]);

    const nextSlide = useCallback((e?: React.MouseEvent) => {
        e?.stopPropagation();
        setSelectedSlideIndex(prev => prev !== null ? Math.min(prev + 1, slides.length - 1) : prev);
    }, [slides.length]);

    const prevSlide = useCallback((e?: React.MouseEvent) => {
        e?.stopPropagation();
        setSelectedSlideIndex(prev => prev !== null ? Math.max(prev - 1, 0) : prev);
    }, []);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (selectedSlideIndex === null) return;
            if (e.key === 'ArrowRight') nextSlide();
            if (e.key === 'ArrowLeft') prevSlide();
            if (e.key === 'Escape') setSelectedSlideIndex(null);
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedSlideIndex, nextSlide, prevSlide]);

    if (slides.length === 0 || renderedSlides.length === 0) return null;

    const handleMouseDown = (e: React.MouseEvent) => {
        if (!scrollContainerRef.current) return;
        setIsDragging(true);
        setHasDragged(false);
        setStartX(e.pageX - scrollContainerRef.current.offsetLeft);
        setScrollLeft(scrollContainerRef.current.scrollLeft);
    };

    const handleMouseMove = (e: React.MouseEvent) => {
        if (!isDragging || !scrollContainerRef.current) return;
        e.preventDefault();
        const x = e.pageX - scrollContainerRef.current.offsetLeft;
        const walk = (x - startX) * 2;
        scrollContainerRef.current.scrollLeft = scrollLeft - walk;
        if (Math.abs(x - startX) > 5) setHasDragged(true);
    };

    const handleSlideClick = (index: number) => {
        if (!hasDragged) setSelectedSlideIndex(index);
    };

    return (
        <div className={`w-full ${className}`}>
            <div
                ref={scrollContainerRef}
                className={`
                    flex overflow-x-auto gap-4 py-4 px-2
                    scrollbar-none
                    ${isDragging ? 'cursor-grabbing' : 'cursor-grab'}
                `}
                onMouseDown={handleMouseDown}
                onMouseLeave={() => setIsDragging(false)}
                onMouseUp={() => setIsDragging(false)}
                onMouseMove={handleMouseMove}
                style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
            >
                <style>{`.scrollbar-none::-webkit-scrollbar { display: none; }`}</style>

                {renderedSlides.map((renderedSlide, index) => {
                    const aspectRatio = slideSize.width / slideSize.height;
                    const thumbnailHeight = 240;
                    const thumbnailWidth = thumbnailHeight * aspectRatio;

                    return (
                        <div
                            key={index}
                            onClick={() => handleSlideClick(index)}
                            className="flex-shrink-0 relative group rounded-xl overflow-hidden border shadow-sm transition-all duration-200 border-slate-200 bg-white select-none"
                            style={{ height: thumbnailHeight, width: thumbnailWidth }}
                        >
                            <div
                                className="absolute top-0 left-0 origin-top-left overflow-hidden pointer-events-none"
                                style={{
                                    width: slideSize.width,
                                    height: slideSize.height,
                                    transform: `scale(${thumbnailHeight / slideSize.height})`,
                                }}
                            >
                                <style dangerouslySetInnerHTML={{ __html: renderedSlide.css }} />
                                <div
                                    className="marp-slide"
                                    dangerouslySetInnerHTML={{ __html: renderedSlide.html }}
                                />
                            </div>
                            <div className="absolute inset-0 bg-black/0 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
                                <Maximize2 className="text-white drop-shadow-md" size={32} />
                            </div>
                            <div className="absolute bottom-2 right-2 bg-black/60 text-white text-[10px] px-2 py-0.5 rounded-full backdrop-blur-sm">
                                {index + 1}
                            </div>
                        </div>
                    );
                })}
            </div>

            {selectedSlideIndex !== null && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/95 backdrop-blur-sm p-4 animate-in fade-in duration-200">
                    <button
                        onClick={() => setSelectedSlideIndex(null)}
                        className="absolute top-6 right-6 p-2 text-white/70 hover:text-white hover:bg-white/10 rounded-full transition-colors z-50"
                    >
                        <X size={32} />
                    </button>
                    <button
                        onClick={prevSlide}
                        disabled={selectedSlideIndex === 0}
                        className={`absolute left-4 md:left-8 p-3 rounded-full transition-colors z-50
                            ${selectedSlideIndex === 0 ? 'text-white/20 cursor-default' : 'text-white/70 hover:text-white hover:bg-white/10'}`}
                    >
                        <ChevronLeft size={48} />
                    </button>
                    <button
                        onClick={nextSlide}
                        disabled={selectedSlideIndex === slides.length - 1}
                        className={`absolute right-4 md:right-8 p-3 rounded-full transition-colors z-50
                            ${selectedSlideIndex === slides.length - 1 ? 'text-white/20 cursor-default' : 'text-white/70 hover:text-white hover:bg-white/10'}`}
                    >
                        <ChevronRight size={48} />
                    </button>
                    <div
                        className="relative max-w-[90vw] max-h-[90vh] w-full flex items-center justify-center"
                        onClick={(e) => e.stopPropagation()}
                        style={{ aspectRatio: `${slideSize.width} / ${slideSize.height}` }}
                    >
                        <SlideScaler width={slideSize.width} height={slideSize.height}>
                            <div
                                className="bg-white rounded-2xl shadow-2xl overflow-hidden relative"
                                style={{ width: slideSize.width, height: slideSize.height }}
                            >
                                {renderedSlides[selectedSlideIndex] && (
                                    <>
                                        <style dangerouslySetInnerHTML={{ __html: renderedSlides[selectedSlideIndex].css }} />
                                        <div className="w-full h-full">
                                            <PostProcessedSlide
                                                html={renderedSlides[selectedSlideIndex].html}
                                                onTickerClick={onTickerClick}
                                                onTagClick={onTagClick}
                                                episodeId={episodeId}
                                                episodeTitle={episodeTitle}
                                                episodeSource={episodeSource}
                                                spotifyUri={spotifyUri}
                                                timestampedSections={timestampedSections}
                                            />
                                        </div>
                                    </>
                                )}
                            </div>
                        </SlideScaler>
                    </div>
                </div>
            )}
        </div>
    );
};
