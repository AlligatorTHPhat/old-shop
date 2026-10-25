export enum Role {
  ADMIN = 'ADMIN',
  MOD = 'MOD',
  SELLER = 'SELLER',
  CUSTOMER = 'CUSTOMER'
}

export interface User {
  user_id: number;
  username: string;
  email: string;
  full_name: string;
  phone_number?: string;
  address?: string;
  avatar_url?: string;
  role?: Role;
  trust_score?: number;
  created_at: string;
  updated_at?: string;
}

export interface VerifyOTPRequest {
  email: string;
  otp: string;
  new_password: string;
}

export interface ProductImage {
  image_id: number;
  image_url: string;
  alt_text?: string;
  is_primary: boolean;
  display_order: number;
}

export interface Review {
  review_id: number;
  product_id: number;
  buyer_id: number;
  rating: number;
  content: string;
  created_at: string;
  reviewer?: User;
}

export interface Product {
  product_id: number;
  title: string;
  description?: string;
  price: number;
  quantity: number;
  category_id: number;
  seller_id: number;
  status: number;
  reject_reason?: string;
  view_count: number;
  video_url?: string;
  condition_rating?: number;  
  warranty_months?: number;
  is_deleted: boolean;
  created_at: string;
  updated_at?: string;
  transfer_method: number;
  is_approved: boolean;
  product_images: ProductImage[];
  seller?: User;
  reviews: Review[];
}

export interface Voucher {
  voucher_id: number;
  code: string;
  description?: string;
  discount_type: number; // 0: Fixed, 1: Percent
  discount_value: number;
  usage_count: number;
  max_usage?: number;
  min_order_amount?: number;
  valid_from: string;
  valid_to: string;
  is_active: boolean;
}

export interface Order {
  order_id: number;
  buyer_id: number;
  total_amount: number;
  discount_amount: number;
  shipping_fee: number;
  final_amount: number;
  order_status: number;
  order_date: string;
  voucher_id?: number;
  voucher?: Voucher;
  order_details: OrderDetail[];
}

export interface OrderDetail {
  id: number;
  orderId: number;
  productId: number;
  quantity: number;
  price: number;
}

export interface Category {
  category_id: number;
  name: string;
  description: string;
  is_deleted: boolean;
  id?: number;
}