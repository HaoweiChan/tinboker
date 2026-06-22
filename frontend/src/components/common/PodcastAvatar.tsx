import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { getAvatarColor } from '@/utils/avatarColor';

interface PodcastAvatarProps {
    name: string;
    src?: string | null;
    size?: 'sm' | 'md' | 'lg' | 'xl';
    className?: string;
}

export const PodcastAvatar: React.FC<PodcastAvatarProps> = ({ name, src, size = 'md', className }) => {
    const [imageError, setImageError] = useState(false);

    const avatarColor = getAvatarColor(name);
    const initial = name.charAt(0).toUpperCase() || 'P';

    const sizeClasses = {
        sm: 'w-8 h-8 text-xs',
        md: 'w-10 h-10 text-base',
        lg: 'w-12 h-12 text-lg',
        xl: 'w-16 h-16 text-xl',
    };

    if (!src || imageError) {
        return (
            <div
                className={cn(
                    'rounded-lg flex items-center justify-center flex-shrink-0 font-bold text-white',
                    sizeClasses[size],
                    className
                )}
                style={{ backgroundColor: avatarColor }}
            >
                {initial}
            </div>
        );
    }

    return (
        <img
            src={src}
            alt={name}
            className={cn(
                'rounded-lg object-cover flex-shrink-0 bg-muted',
                sizeClasses[size],
                className
            )}
            onError={() => setImageError(true)}
        />
    );
};
