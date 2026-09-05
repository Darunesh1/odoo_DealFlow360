/** Mirrors Role in backend/app/models/user.py. A user may hold several. */
export const ROLES = ["admin", "sales_rep", "sales_manager", "finance", "customer"] as const

export type Role = (typeof ROLES)[number]

/** Human labels for each role, used everywhere a role is displayed. */
export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  sales_rep: "Sales Rep",
  sales_manager: "Sales Manager",
  finance: "Finance / Ops",
  customer: "Customer",
}

export interface User {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  /** False while an invitation has been sent but not yet accepted. */
  is_verified: boolean
  roles: Role[]
  created_at: string
  updated_at: string
}

export const PRODUCT_UNITS = ["each", "hour", "day", "license", "recurring"] as const
export type ProductUnit = (typeof PRODUCT_UNITS)[number]

export const RECURRING_INTERVALS = ["weekly", "monthly", "quarterly", "yearly"] as const
export type RecurringInterval = (typeof RECURRING_INTERVALS)[number]

export const PRODUCT_STATUSES = ["active", "archived"] as const
export type ProductStatus = (typeof PRODUCT_STATUSES)[number]

export const LINE_SOURCES = ["manual", "upsell", "cross_sell"] as const
export type LineSource = (typeof LINE_SOURCES)[number]

export const QUOTATION_STATUSES = [
  "draft",
  "pending_approval",
  "approved",
  "rejected",
  "negotiation",
  "confirmed",
  "cancelled",
] as const
export type QuotationStatus = (typeof QUOTATION_STATUSES)[number]

export const RISK_BANDS = ["none", "low", "medium", "high"] as const
export type RiskBand = (typeof RISK_BANDS)[number]

/** The stage chips above the quotation list, and the Kanban columns. */
export const QUOTATION_STAGE_LABELS: Record<QuotationStatus, string> = {
  draft: "Draft",
  pending_approval: "Pending Approval",
  approved: "Approved",
  negotiation: "Negotiation",
  confirmed: "Confirmed",
  rejected: "Rejected",
  cancelled: "Cancelled",
}

/** Left to right, the order a deal actually moves through. */
export const PIPELINE_STAGES = [
  "draft",
  "pending_approval",
  "approved",
  "negotiation",
  "confirmed",
] as const satisfies readonly QuotationStatus[]

export const QUOTATION_SORTS = [
  "number",
  "customer",
  "total",
  "status",
  "risk",
  "updated",
] as const
export type QuotationSort = (typeof QUOTATION_SORTS)[number]

export const APPROVAL_STATUSES = [
  "pending",
  "approved",
  "auto_approved",
  "returned",
  "rejected",
  "cancelled",
] as const
export type ApprovalStatus = (typeof APPROVAL_STATUSES)[number]

export const APPROVAL_STEP_STATUSES = [
  "pending",
  "approved",
  "returned",
  "rejected",
  "skipped",
] as const
export type ApprovalStepStatus = (typeof APPROVAL_STEP_STATUSES)[number]

export const APPROVAL_TRIGGERS = ["rep_submit", "rep_resubmit", "customer_counter"] as const
export type ApprovalTrigger = (typeof APPROVAL_TRIGGERS)[number]

/** The name is the natural key: there is no code, and no sort order. */
export interface CustomerTier {
  id: string
  name: string
  max_discount_percent: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Currency {
  code: string
  name: string
  symbol: string
  /** One unit of this currency in the base currency; the base row is 1. */
  rate_to_base: number
  is_base: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

/** A category with no row here has NO ceiling, which is not a ceiling of zero. */
export interface CategoryLimit {
  id: string
  category: string
  max_discount_percent: number
  created_at: string
  updated_at: string
}

export interface Customer {
  id: string
  name: string
  tier_id: string
  contact_email: string | null
  phone: string | null
  billing_address: string | null
  is_active: boolean
  created_at: string
  updated_at: string
  tier: CustomerTier
}

/** A derived cell: base price converted, less that tier's discount. */
export interface VariantPrice {
  tier_id: string
  currency_code: string
  unit_price: number
}

export interface VariantStock {
  warehouse_id: string
  quantity_on_hand: number
  quantity_reserved: number
  quantity_available: number
}

export interface VariantAttributeValue {
  id: string
  value: string
  position: number
}

export interface VariantAttribute {
  id: string
  name: string
  position: number
  values: VariantAttributeValue[]
}

/** One sellable combination. The only thing that carries a SKU. */
export interface ProductVariant {
  id: string
  sku: string
  name: string
  options: Record<string, string>
  /** The two numbers an admin types, both in the base currency. */
  unit_cost: number
  base_price: number
  is_default: boolean
  is_active: boolean
  prices: VariantPrice[]
  stock: VariantStock[]
}

export interface Product {
  id: string
  name: string
  /** Free text; the form suggests names already in use. */
  category: string
  description: string | null
  unit: ProductUnit
  tax_percent: number
  is_subscription: boolean
  recurring_interval: RecurringInterval | null
  has_variants: boolean
  is_promoted: boolean
  promotion_label: string | null
  status: ProductStatus
  created_at: string
  updated_at: string
  attributes: VariantAttribute[]
  variants: ProductVariant[]
}

/** One row of the product catalog table (screen 16). */
export interface ProductListRow {
  id: string
  name: string
  category: string
  unit: ProductUnit
  tax_percent: number
  status: ProductStatus
  has_variants: boolean
  is_subscription: boolean
  recurring_interval: RecurringInterval | null
  variant_count: number
  price_min: number | null
  price_max: number | null
  base_currency: string
}

/** The three KPI boxes on the product catalog screen. */
export const PRODUCT_SORTS = [
  "name",
  "category",
  "variants",
  "price",
  "tax",
  "status",
] as const
export type ProductSort = (typeof PRODUCT_SORTS)[number]

export interface CatalogStats {
  products_active: number
  products_archived: number
  tier_count: number
  currency_count: number
  sku_count: number
}

export interface PriceMatrixRow {
  product_id: string
  product_name: string
  variant_id: string
  variant_name: string
  sku: string
  tier_name: string
  currency_code: string
  unit_price: number
}

export interface Warehouse {
  id: string
  code: string
  name: string
  address: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface StockItem {
  id: string
  warehouse_id: string
  variant_id: string
  quantity_on_hand: number
  quantity_reserved: number
  quantity_available: number
  reorder_point: number
  reorder_quantity: number
  lead_time_days: number
  bin_location: string | null
  created_at: string
  updated_at: string
  warehouse_name: string
  warehouse_code: string
  product_id: string
  product_name: string
  variant_name: string
  sku: string
}

export interface QuotationLine {
  id: string
  quotation_id: string
  position: number
  product_id: string | null
  variant_id: string | null
  warehouse_id: string | null
  product_name: string
  variant_name: string | null
  sku: string | null
  category: string | null
  warehouse_name: string | null
  warehouse_code: string | null
  warehouse_bin_location: string | null
  stock_available_at_entry: number | null
  quantity: number
  unit_price: number
  list_price_at_entry: number
  unit_cost: number
  tax_percent: number
  line_discount_percent: number
  discount_percent: number
  tier_limit_percent: number | null
  category_limit_percent: number | null
  allowed_discount_percent: number
  over_by_points: number
  line_net: number
  line_tax: number
  line_total: number
  is_recurring: boolean
  recurring_interval: RecurringInterval | null
  selected_options: Record<string, string>
  source: LineSource
  upsell_source_product_id: string | null
  created_at: string
  updated_at: string
}

export interface ApprovalStep {
  id: string
  approval_id: string
  step_order: number
  role: Role
  status: ApprovalStepStatus
  assignee_id: string | null
  assignee_name: string | null
  decided_by_id: string | null
  decided_by_name: string | null
  decided_at: string | null
  note: string | null
}

export interface Approval {
  id: string
  quotation_id: string
  round_number: number
  rule_id: string | null
  rule_name: string
  blended_risk_score: number
  risk_band: RiskBand
  quotation_total: number
  discount_total: number
  status: ApprovalStatus
  trigger: ApprovalTrigger
  submitted_by_id: string | null
  submitted_by_name: string
  submitted_at: string
  decided_at: string | null
  steps: ApprovalStep[]
  line_snapshots: ApprovalLineSnapshot[]
}

/** One row of the approval screen's "Why This Quote Was Flagged" table. */
export interface ApprovalLineSnapshot {
  id: string
  line_id: string | null
  position: number
  line_label: string
  discount_percent: number
  allowed_discount_percent: number
  over_by_points: number
  line_net: number
}

export interface Quotation {
  id: string
  number: string
  customer_id: string
  recipient_email: string | null
  owner_id: string | null
  owner_name: string | null
  sales_team_id: string | null
  status: QuotationStatus
  currency: string
  customer_tier_id: string | null
  tier_max_discount_percent: number | null
  order_discount_percent: number
  subtotal: number
  discount_total: number
  tax_total: number
  total: number
  margin_total: number
  blended_risk_score: number
  risk_band: RiskBand
  max_line_over_points: number
  weighted_over_points: number
  requires_approval: boolean
  current_round: number
  requested_delivery_date: string | null
  promised_delivery_date: string | null
  valid_until: string | null
  last_activity_at: string | null
  confirmed_at: string | null
  notes: string | null
  created_at: string
  updated_at: string
  customer: Customer
  customer_tier: CustomerTier | null
  lines: QuotationLine[]
  approval: Approval | null
}

export const APPROVAL_DECISIONS = ["approve", "return", "reject"] as const
export type ApprovalDecision = (typeof APPROVAL_DECISIONS)[number]

/** One row of the approvals list. */
export interface ApprovalListRow {
  id: string
  quotation_id: string
  quotation_number: string
  customer_name: string
  customer_tier: string | null
  round_number: number
  rule_name: string
  blended_risk_score: number
  risk_band: RiskBand
  quotation_total: number
  currency: string
  status: ApprovalStatus
  current_role: Role | null
  assigned_to: string | null
  submitted_by_name: string
  submitted_at: string
  decided_at: string | null
  can_act: boolean
}

export interface ApprovalCounts {
  pending: number
  returned: number
  approved: number
  rejected: number
}

export interface ApprovalListPage extends Page<ApprovalListRow> {
  counts: ApprovalCounts
}

/** One line of the audit trail. */
export interface AuditEntry {
  id: string
  action: string
  actor_name: string
  reason: string | null
  context: Record<string, unknown> | null
  created_at: string
}

export interface ApprovalDetail extends Approval {
  quotation_number: string
  customer_name: string
  customer_tier: string | null
  currency: string
  current_role: Role | null
  can_act: boolean
  audit_trail: AuditEntry[]
}

/** One card or table row on the quotations list. */
export interface QuotationListRow {
  id: string
  number: string
  customer_id: string
  customer_name: string
  customer_tier: string | null
  owner_name: string | null
  status: QuotationStatus
  currency: string
  total: number
  margin_total: number
  line_count: number
  risk_band: RiskBand
  blended_risk_score: number
  requires_approval: boolean
  valid_until: string | null
  last_activity_at: string | null
  updated_at: string
}

export type QuotationStageCounts = Record<QuotationStatus, number>

export interface QuotationListPage extends Page<QuotationListRow> {
  counts: QuotationStageCounts
}

/** One card in the upsell and cross-sell panel. */
export interface UpsellSuggestion {
  product_id: string
  variant_id: string
  name: string
  category: string
  sku: string
  unit_price: number
  unit_cost: number
  margin_delta: number
  margin_percent: number
  is_promoted: boolean
  promotion_label: string | null
  is_recurring: boolean
  reason: string
}

export interface QuotationSubmitResponse {
  quotation: Quotation
  approval_required: boolean
  approval: Approval | null
}

export interface CustomerTierCreateInput {
  name: string
  max_discount_percent: number
  is_active?: boolean
}

export interface CustomerTierUpdateInput {
  name?: string
  max_discount_percent?: number
  is_active?: boolean
}

export interface CurrencyCreateInput {
  code: string
  name: string
  symbol?: string
  rate_to_base: number
  is_active?: boolean
}

export interface CurrencyUpdateInput {
  name?: string
  symbol?: string
  rate_to_base?: number
  is_active?: boolean
}

export interface CategoryLimitCreateInput {
  category: string
  max_discount_percent: number
}

export interface CategoryLimitUpdateInput {
  category?: string
  max_discount_percent?: number
}

export interface VariantAttributeInput {
  name: string
  values: string[]
}

export interface ProductCreateInput {
  name: string
  category: string
  description?: string | null
  unit?: ProductUnit
  tax_percent?: number
  is_subscription?: boolean
  recurring_interval?: RecurringInterval | null
  has_variants?: boolean
  is_promoted?: boolean
  promotion_label?: string | null
  attributes?: VariantAttributeInput[]
}

export interface ProductUpdateInput {
  name?: string
  category?: string
  description?: string | null
  unit?: ProductUnit
  tax_percent?: number
  is_subscription?: boolean
  recurring_interval?: RecurringInterval | null
  has_variants?: boolean
  is_promoted?: boolean
  promotion_label?: string | null
  attributes?: VariantAttributeInput[]
}

/** One row of the generated-variants table, as the admin filled it in. */
export interface VariantRowInput {
  id: string
  sku: string
  /** Both required and both in the base currency. */
  unit_cost: number
  base_price: number
  is_active?: boolean
  /** Required for every active warehouse unless the product is a subscription. */
  stock: { warehouse_id: string; quantity_on_hand: number }[]
}

export interface VariantMatrixSaveInput {
  rows: VariantRowInput[]
}

export interface WarehouseCreateInput {
  code: string
  name: string
  address?: string | null
  is_active?: boolean
}

export interface WarehouseUpdateInput {
  code?: string
  name?: string
  address?: string | null
  is_active?: boolean
}

export interface StockUpsertInput {
  warehouse_id: string
  product_id: string
  quantity_on_hand: number
  quantity_reserved?: number
  reorder_point?: number
  reorder_quantity?: number
  lead_time_days?: number
  bin_location?: string | null
}

export interface CustomerCreateInput {
  name: string
  tier_id: string
  contact_email?: string | null
  phone?: string | null
  billing_address?: string | null
  is_active?: boolean
}

export interface CustomerUpdateInput {
  name?: string
  tier_id?: string
  contact_email?: string | null
  phone?: string | null
  billing_address?: string | null
  is_active?: boolean
}

export interface QuotationCreateInput {
  customer_id: string
  currency?: string
  recipient_email?: string | null
  order_discount_percent?: number
  notes?: string | null
  requested_delivery_date?: string | null
  valid_until?: string | null
}

export interface QuotationUpdateInput {
  recipient_email?: string | null
  order_discount_percent?: number
  notes?: string | null
  requested_delivery_date?: string | null
  promised_delivery_date?: string | null
  valid_until?: string | null
}

export interface QuotationLineCreateInput {
  /** The variant carries the SKU, the stock and the tier price. */
  variant_id: string
  quantity: number
  line_discount_percent?: number
  source?: LineSource
}

export interface QuotationLineUpdateInput {
  quantity?: number
  line_discount_percent?: number
  source?: LineSource
}

export interface QuotationDiscountUpdateInput {
  order_discount_percent: number
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface Message {
  message: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

/** Shape of FastAPI's error responses: a string, or a list of validation errors. */
export interface ApiErrorBody {
  detail?: string | { msg: string; loc?: (string | number)[] }[]
}
