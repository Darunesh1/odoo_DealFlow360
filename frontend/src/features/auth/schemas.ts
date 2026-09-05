import { z } from "zod"

import { ROLES } from "@/types/api"

/** Mirrors the backend rule in backend/app/schemas/user.py: 8+ chars, a letter and a digit. */
export const passwordSchema = z
  .string()
  .min(8, "Use at least 8 characters")
  .max(128, "Use at most 128 characters")
  .regex(/[A-Za-z]/, "Include at least one letter")
  .regex(/[0-9]/, "Include at least one digit")

export const emailSchema = z.email("Enter a valid email address")

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Enter your password"),
})

/**
 * Public sign-up. Everyone who registers becomes a customer - the backend
 * forces the role, and there is no field here that could ask for another.
 */
export const signupSchema = z
  .object({
    full_name: z.string().min(1, "Enter your name").max(255),
    company_name: z.string().max(255).optional(),
    email: emailSchema,
    password: passwordSchema,
    confirm_password: z.string(),
  })
  .refine((values) => values.password === values.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  })

/** Admins create internal accounts; only customers can sign themselves up. */
export const inviteUserSchema = z.object({
  full_name: z.string().min(1, "Enter their name").max(255),
  email: emailSchema,
  roles: z.array(z.enum(ROLES)).min(1, "Pick at least one role"),
})

/** The invitee sets their first password from the emailed link. */
export const acceptInviteSchema = z
  .object({
    new_password: passwordSchema,
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  })

export const forgotPasswordSchema = z.object({ email: emailSchema })

export const resetPasswordSchema = z
  .object({
    new_password: passwordSchema,
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  })

export const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password"),
    new_password: passwordSchema,
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  })
  .refine((values) => values.current_password !== values.new_password, {
    message: "Choose a password different from your current one",
    path: ["new_password"],
  })

export const profileSchema = z.object({
  full_name: z.string().min(1, "Enter your name").max(255),
  email: emailSchema,
})

export type LoginValues = z.infer<typeof loginSchema>
export type SignupValues = z.infer<typeof signupSchema>
export type InviteUserValues = z.infer<typeof inviteUserSchema>
export type AcceptInviteValues = z.infer<typeof acceptInviteSchema>
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>
export type ProfileValues = z.infer<typeof profileSchema>
