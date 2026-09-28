import { z } from 'zod';

export const SessionUserSchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  email: z.string(),
  avatar: z.string().nullish(),
  member_until: z.string().nullable().optional(),
  is_member: z.boolean().default(false),
  membership_preview: z.enum(['free', 'paid']).nullable().default(null),
  membership_preview_available: z.boolean().default(false),
});

export const SessionResponseSchema = z.object({
  token: z.string().min(1),
  refresh_token: z.string().min(1).optional(),
  user: SessionUserSchema,
});

export function sessionUser(data: z.input<typeof SessionUserSchema>) {
  const user = SessionUserSchema.parse(data);
  return {
    ...user,
    avatar: user.avatar || '',
    initials: user.name.split(' ').map((name) => name[0]).join('').toUpperCase().slice(0, 2),
    member_until: user.member_until ?? null,
  };
}
