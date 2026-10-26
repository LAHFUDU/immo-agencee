"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-21 00:15:38.285369
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence('customer_ref_seq')))
    op.execute(sa.schema.CreateSequence(sa.Sequence('request_ref_seq')))
    op.execute(sa.schema.CreateSequence(sa.Sequence('property_ref_seq')))
    op.execute(sa.schema.CreateSequence(sa.Sequence('deal_ref_seq')))
    op.create_table('permissions',
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('module', sa.String(length=32), nullable=False),
    sa.Column('label', sa.String(length=160), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_permissions')),
    sa.UniqueConstraint('code', name=op.f('uq_permissions_code'))
    )
    op.create_table('property_categories',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('label', sa.String(length=80), nullable=False),
    sa.Column('has_rooms', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_property_categories'))
    )
    op.create_table('property_features',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('label', sa.String(length=80), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_property_features'))
    )
    op.create_table('rate_limit_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rate_limit_events'))
    )
    op.create_index('ix_rate_limit_events_key_created', 'rate_limit_events', ['key', 'created_at'], unique=False)
    op.create_table('roles',
    sa.Column('code', sa.String(length=48), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_system', sa.Boolean(), nullable=False),
    sa.Column('is_superadmin', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_roles')),
    sa.UniqueConstraint('code', name=op.f('uq_roles_code'))
    )
    op.create_table('commission_rules',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('transaction_type', sa.Enum('sale', 'rent', name='transaction_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('property_type', sa.String(length=32), nullable=True),
    sa.Column('min_price', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('max_price', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('rate_percent', sa.Numeric(precision=6, scale=3), nullable=False),
    sa.Column('fixed_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('fixed_amount >= 0', name=op.f('ck_commission_rules_fixed_positive')),
    sa.CheckConstraint('rate_percent >= 0 AND rate_percent <= 100', name=op.f('ck_commission_rules_rate_range')),
    sa.ForeignKeyConstraint(['property_type'], ['property_categories.code'], name=op.f('fk_commission_rules_property_type_property_categories'), onupdate='CASCADE', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_commission_rules'))
    )
    op.create_table('role_permissions',
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('permission_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], name=op.f('fk_role_permissions_permission_id_permissions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_role_permissions_role_id_roles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('role_id', 'permission_id', name=op.f('pk_role_permissions'))
    )
    op.create_table('users',
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('full_name', sa.String(length=160), nullable=False),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('job_title', sa.String(length=120), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=True),
    sa.Column('role_id', sa.UUID(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('must_change_password', sa.Boolean(), nullable=False),
    sa.Column('is_agent', sa.Boolean(), nullable=False),
    sa.Column('language', sa.String(length=8), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], name=op.f('fk_users_role_id_roles'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index('uq_users_email_lower', 'users', [sa.literal_column('lower(email)')], unique=True)
    op.create_table('app_settings',
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_app_settings_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_app_settings'))
    )
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=48), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('entity_label', sa.String(length=200), nullable=True),
    sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_audit_logs_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)
    op.create_index('ix_audit_logs_entity', 'audit_logs', ['entity_type', 'entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_table('auth_tokens',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('purpose', sa.Enum('invite', 'reset', name='token_purpose', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_auth_tokens_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_auth_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_auth_tokens_token_hash'))
    )
    op.create_index(op.f('ix_auth_tokens_user_id'), 'auth_tokens', ['user_id'], unique=False)
    op.create_table('customers',
    sa.Column('reference', sa.String(length=32), nullable=False),
    sa.Column('full_name', sa.String(length=160), nullable=False),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('phone_key', sa.String(length=32), nullable=True),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('preferred_contact', sa.Enum('phone', 'email', 'whatsapp', 'sms', 'any', name='contact_method', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('source', sa.Enum('website', 'referral', 'phone', 'walk_in', 'social_media', 'portal', 'other', name='customer_source', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('preferences', sa.Text(), nullable=True),
    sa.Column('internal_notes', sa.Text(), nullable=True),
    sa.Column('assigned_agent_id', sa.UUID(), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assigned_agent_id'], ['users.id'], name=op.f('fk_customers_assigned_agent_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_customers_created_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_customers')),
    sa.UniqueConstraint('reference', name=op.f('uq_customers_reference'))
    )
    op.create_index(op.f('ix_customers_assigned_agent_id'), 'customers', ['assigned_agent_id'], unique=False)
    op.create_index('ix_customers_email_lower', 'customers', [sa.literal_column('lower(email)')], unique=False)
    op.create_index('ix_customers_name_lower', 'customers', [sa.literal_column('lower(full_name)')], unique=False)
    op.create_index(op.f('ix_customers_phone_key'), 'customers', ['phone_key'], unique=False)
    op.create_table('notifications',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=48), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('link', sa.String(length=255), nullable=True),
    sa.Column('entity_type', sa.String(length=48), nullable=True),
    sa.Column('entity_id', sa.Uuid(), nullable=True),
    sa.Column('dedupe_key', sa.String(length=200), nullable=True),
    sa.Column('is_read', sa.Boolean(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('email_status', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notifications_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
    sa.UniqueConstraint('user_id', 'dedupe_key', name='uq_notifications_user_dedupe')
    )
    op.create_index('ix_notifications_user_unread', 'notifications', ['user_id', 'is_read', 'created_at'], unique=False)
    op.create_table('owners',
    sa.Column('full_name', sa.String(length=160), nullable=False),
    sa.Column('phone', sa.String(length=32), nullable=True),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('company', sa.String(length=160), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_owners_created_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_owners'))
    )
    op.create_table('saved_filters',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('page', sa.String(length=48), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_saved_filters_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_saved_filters'))
    )
    op.create_index(op.f('ix_saved_filters_user_id'), 'saved_filters', ['user_id'], unique=False)
    op.create_table('user_sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_token', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_sessions_token_hash'))
    )
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_table('customer_requests',
    sa.Column('reference', sa.String(length=32), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('property_type', sa.String(length=32), nullable=False),
    sa.Column('transaction_type', sa.Enum('sale', 'rent', name='transaction_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('budget_min', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('budget_max', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('city_key', sa.String(length=100), nullable=False),
    sa.Column('neighborhood', sa.String(length=120), nullable=True),
    sa.Column('neighborhood_key', sa.String(length=120), nullable=True),
    sa.Column('surface_min', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('surface_max', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('bedrooms_min', sa.Integer(), nullable=True),
    sa.Column('bathrooms_min', sa.Integer(), nullable=True),
    sa.Column('required_features', postgresql.ARRAY(sa.String(length=32)), nullable=False),
    sa.Column('preferred_features', postgresql.ARRAY(sa.String(length=32)), nullable=False),
    sa.Column('comments', sa.Text(), nullable=True),
    sa.Column('internal_notes', sa.Text(), nullable=True),
    sa.Column('priority', sa.Enum('low', 'normal', 'high', 'urgent', name='priority', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status', sa.Enum('new', 'to_contact', 'contacted', 'proposed', 'visit_scheduled', 'negotiation', 'converted', 'closed_lost', 'archived', name='request_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('source', sa.Enum('website', 'referral', 'phone', 'walk_in', 'social_media', 'portal', 'other', name='customer_source', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('assigned_agent_id', sa.UUID(), nullable=True),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_follow_up_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('first_contacted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('close_reason', sa.String(length=255), nullable=True),
    sa.Column('follow_up_reminded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max', name=op.f('ck_customer_requests_budget_range')),
    sa.CheckConstraint('surface_min IS NULL OR surface_max IS NULL OR surface_min <= surface_max', name=op.f('ck_customer_requests_surface_range')),
    sa.ForeignKeyConstraint(['assigned_agent_id'], ['users.id'], name=op.f('fk_customer_requests_assigned_agent_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_customer_requests_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_customer_requests_customer_id_customers'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['property_type'], ['property_categories.code'], name=op.f('fk_customer_requests_property_type_property_categories'), onupdate='CASCADE', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_customer_requests')),
    sa.UniqueConstraint('reference', name=op.f('uq_customer_requests_reference'))
    )
    op.create_index(op.f('ix_customer_requests_assigned_agent_id'), 'customer_requests', ['assigned_agent_id'], unique=False)
    op.create_index('ix_customer_requests_created_at', 'customer_requests', ['created_at'], unique=False)
    op.create_index(op.f('ix_customer_requests_customer_id'), 'customer_requests', ['customer_id'], unique=False)
    op.create_index('ix_customer_requests_match', 'customer_requests', ['status', 'transaction_type', 'property_type', 'city_key'], unique=False)
    op.create_index(op.f('ix_customer_requests_next_follow_up_at'), 'customer_requests', ['next_follow_up_at'], unique=False)
    op.create_table('properties',
    sa.Column('reference', sa.String(length=32), nullable=False),
    sa.Column('property_type', sa.String(length=32), nullable=False),
    sa.Column('transaction_type', sa.Enum('sale', 'rent', name='transaction_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('city_key', sa.String(length=100), nullable=False),
    sa.Column('neighborhood', sa.String(length=120), nullable=True),
    sa.Column('neighborhood_key', sa.String(length=120), nullable=True),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('surface', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('price', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('bedrooms', sa.Integer(), nullable=True),
    sa.Column('bathrooms', sa.Integer(), nullable=True),
    sa.Column('floor', sa.Integer(), nullable=True),
    sa.Column('features', postgresql.ARRAY(sa.String(length=32)), nullable=False),
    sa.Column('status', sa.Enum('available', 'reserved', 'under_negotiation', 'sold', 'rented', 'unavailable', 'archived', name='property_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status_changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_published', sa.Boolean(), nullable=False),
    sa.Column('latitude', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('longitude', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('internal_notes', sa.Text(), nullable=True),
    sa.Column('owner_id', sa.UUID(), nullable=True),
    sa.Column('responsible_id', sa.UUID(), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('bathrooms IS NULL OR bathrooms >= 0', name=op.f('ck_properties_bathrooms_positive')),
    sa.CheckConstraint('bedrooms IS NULL OR bedrooms >= 0', name=op.f('ck_properties_bedrooms_positive')),
    sa.CheckConstraint('price >= 0', name=op.f('ck_properties_price_positive')),
    sa.CheckConstraint('surface IS NULL OR surface > 0', name=op.f('ck_properties_surface_positive')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_properties_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['owners.id'], name=op.f('fk_properties_owner_id_owners'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['property_type'], ['property_categories.code'], name=op.f('fk_properties_property_type_property_categories'), onupdate='CASCADE', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['responsible_id'], ['users.id'], name=op.f('fk_properties_responsible_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_properties')),
    sa.UniqueConstraint('reference', name=op.f('uq_properties_reference'))
    )
    op.create_index('ix_properties_created_at', 'properties', ['created_at'], unique=False)
    op.create_index('ix_properties_features', 'properties', ['features'], unique=False, postgresql_using='gin')
    op.create_index('ix_properties_match', 'properties', ['status', 'transaction_type', 'property_type', 'city_key'], unique=False)
    op.create_index(op.f('ix_properties_owner_id'), 'properties', ['owner_id'], unique=False)
    op.create_index(op.f('ix_properties_responsible_id'), 'properties', ['responsible_id'], unique=False)
    op.create_table('deals',
    sa.Column('reference', sa.String(length=32), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('request_id', sa.UUID(), nullable=True),
    sa.Column('property_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=True),
    sa.Column('transaction_type', sa.Enum('sale', 'rent', name='transaction_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status', sa.Enum('negotiation', 'reserved', 'won', 'lost', 'cancelled', name='deal_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('asking_price', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('agreed_price', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('commission_rule_id', sa.UUID(), nullable=True),
    sa.Column('commission_rate', sa.Numeric(precision=6, scale=3), nullable=True),
    sa.Column('commission_amount', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('commission_overridden', sa.Boolean(), nullable=False),
    sa.Column('expected_closing_date', sa.Date(), nullable=True),
    sa.Column('actual_closing_date', sa.Date(), nullable=True),
    sa.Column('lost_reason', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('holds_reservation', sa.Boolean(), nullable=False),
    sa.Column('reservation_override', sa.Boolean(), nullable=False),
    sa.Column('reservation_override_by_id', sa.UUID(), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('agreed_price IS NULL OR agreed_price >= 0', name=op.f('ck_deals_agreed_price_positive')),
    sa.ForeignKeyConstraint(['agent_id'], ['users.id'], name=op.f('fk_deals_agent_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['commission_rule_id'], ['commission_rules.id'], name=op.f('fk_deals_commission_rule_id_commission_rules'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_deals_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_deals_customer_id_customers'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], name=op.f('fk_deals_property_id_properties'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['request_id'], ['customer_requests.id'], name=op.f('fk_deals_request_id_customer_requests'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reservation_override_by_id'], ['users.id'], name=op.f('fk_deals_reservation_override_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deals')),
    sa.UniqueConstraint('reference', name=op.f('uq_deals_reference'))
    )
    op.create_index(op.f('ix_deals_agent_id'), 'deals', ['agent_id'], unique=False)
    op.create_index(op.f('ix_deals_customer_id'), 'deals', ['customer_id'], unique=False)
    op.create_index(op.f('ix_deals_property_id'), 'deals', ['property_id'], unique=False)
    op.create_index(op.f('ix_deals_request_id'), 'deals', ['request_id'], unique=False)
    op.create_index('uq_deals_single_reservation', 'deals', ['property_id'], unique=True, postgresql_where=sa.text('holds_reservation AND NOT reservation_override'))
    op.create_table('matches',
    sa.Column('request_id', sa.UUID(), nullable=False),
    sa.Column('property_id', sa.UUID(), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('category', sa.Enum('exact', 'strong', 'partial', 'ineligible', name='match_category', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('explanation', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('status', sa.Enum('suggested', 'proposed', 'interested', 'visit_scheduled', 'rejected', name='match_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('customer_feedback', sa.Text(), nullable=True),
    sa.Column('rejection_reason', sa.String(length=255), nullable=True),
    sa.Column('proposed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notified_signature', sa.String(length=120), nullable=True),
    sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], name=op.f('fk_matches_property_id_properties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['request_id'], ['customer_requests.id'], name=op.f('fk_matches_request_id_customer_requests'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_matches')),
    sa.UniqueConstraint('request_id', 'property_id', name='uq_matches_request_property')
    )
    op.create_index(op.f('ix_matches_property_id'), 'matches', ['property_id'], unique=False)
    op.create_index('ix_matches_request_active', 'matches', ['request_id', 'is_active'], unique=False)
    op.create_table('property_documents',
    sa.Column('property_id', sa.UUID(), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=64), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(length=160), nullable=True),
    sa.Column('is_confidential', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('uploaded_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], name=op.f('fk_property_documents_property_id_properties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], name=op.f('fk_property_documents_uploaded_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_property_documents'))
    )
    op.create_index(op.f('ix_property_documents_property_id'), 'property_documents', ['property_id'], unique=False)
    op.create_table('property_photos',
    sa.Column('property_id', sa.UUID(), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=64), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('uploaded_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], name=op.f('fk_property_photos_property_id_properties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], name=op.f('fk_property_photos_uploaded_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_property_photos'))
    )
    op.create_index(op.f('ix_property_photos_property_id'), 'property_photos', ['property_id'], unique=False)
    op.create_table('tasks',
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('open', 'done', 'cancelled', name='task_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('assigned_to_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=True),
    sa.Column('request_id', sa.UUID(), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reminded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assigned_to_id'], ['users.id'], name=op.f('fk_tasks_assigned_to_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_tasks_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_tasks_customer_id_customers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['request_id'], ['customer_requests.id'], name=op.f('fk_tasks_request_id_customer_requests'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tasks'))
    )
    op.create_index(op.f('ix_tasks_assigned_to_id'), 'tasks', ['assigned_to_id'], unique=False)
    op.create_index(op.f('ix_tasks_due_at'), 'tasks', ['due_at'], unique=False)
    op.create_table('activities',
    sa.Column('type', sa.Enum('call', 'meeting', 'email', 'whatsapp', 'sms', 'visit', 'offer', 'note', 'web_contact', 'status_change', name='activity_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=True),
    sa.Column('request_id', sa.UUID(), nullable=True),
    sa.Column('property_id', sa.UUID(), nullable=True),
    sa.Column('deal_id', sa.UUID(), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_activities_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_activities_customer_id_customers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_activities_deal_id_deals'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], name=op.f('fk_activities_property_id_properties'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['request_id'], ['customer_requests.id'], name=op.f('fk_activities_request_id_customer_requests'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_activities'))
    )
    op.create_index(op.f('ix_activities_customer_id'), 'activities', ['customer_id'], unique=False)
    op.create_index(op.f('ix_activities_deal_id'), 'activities', ['deal_id'], unique=False)
    op.create_index(op.f('ix_activities_request_id'), 'activities', ['request_id'], unique=False)
    op.create_table('offers',
    sa.Column('deal_id', sa.UUID(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('party', sa.Enum('customer', 'owner', name='offer_party', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status', sa.Enum('pending', 'accepted', 'rejected', 'countered', 'withdrawn', name='offer_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('offered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('amount >= 0', name=op.f('ck_offers_amount_positive')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_offers_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_offers_deal_id_deals'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_offers'))
    )
    op.create_index(op.f('ix_offers_deal_id'), 'offers', ['deal_id'], unique=False)
    op.create_table('visits',
    sa.Column('request_id', sa.UUID(), nullable=True),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('property_id', sa.UUID(), nullable=False),
    sa.Column('match_id', sa.UUID(), nullable=True),
    sa.Column('agent_id', sa.UUID(), nullable=True),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('duration_minutes', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('scheduled', 'done', 'cancelled', 'no_show', name='visit_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('customer_feedback', sa.Text(), nullable=True),
    sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['users.id'], name=op.f('fk_visits_agent_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_visits_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_visits_customer_id_customers'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['match_id'], ['matches.id'], name=op.f('fk_visits_match_id_matches'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], name=op.f('fk_visits_property_id_properties'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['request_id'], ['customer_requests.id'], name=op.f('fk_visits_request_id_customer_requests'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_visits'))
    )
    op.create_index(op.f('ix_visits_agent_id'), 'visits', ['agent_id'], unique=False)
    op.create_index(op.f('ix_visits_customer_id'), 'visits', ['customer_id'], unique=False)
    op.create_index(op.f('ix_visits_property_id'), 'visits', ['property_id'], unique=False)
    op.create_index(op.f('ix_visits_request_id'), 'visits', ['request_id'], unique=False)
    op.create_index(op.f('ix_visits_scheduled_at'), 'visits', ['scheduled_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_visits_scheduled_at'), table_name='visits')
    op.drop_index(op.f('ix_visits_request_id'), table_name='visits')
    op.drop_index(op.f('ix_visits_property_id'), table_name='visits')
    op.drop_index(op.f('ix_visits_customer_id'), table_name='visits')
    op.drop_index(op.f('ix_visits_agent_id'), table_name='visits')
    op.drop_table('visits')
    op.drop_index(op.f('ix_offers_deal_id'), table_name='offers')
    op.drop_table('offers')
    op.drop_index(op.f('ix_activities_request_id'), table_name='activities')
    op.drop_index(op.f('ix_activities_deal_id'), table_name='activities')
    op.drop_index(op.f('ix_activities_customer_id'), table_name='activities')
    op.drop_table('activities')
    op.drop_index(op.f('ix_tasks_due_at'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_assigned_to_id'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_index(op.f('ix_property_photos_property_id'), table_name='property_photos')
    op.drop_table('property_photos')
    op.drop_index(op.f('ix_property_documents_property_id'), table_name='property_documents')
    op.drop_table('property_documents')
    op.drop_index('ix_matches_request_active', table_name='matches')
    op.drop_index(op.f('ix_matches_property_id'), table_name='matches')
    op.drop_table('matches')
    op.drop_index('uq_deals_single_reservation', table_name='deals', postgresql_where=sa.text('holds_reservation AND NOT reservation_override'))
    op.drop_index(op.f('ix_deals_request_id'), table_name='deals')
    op.drop_index(op.f('ix_deals_property_id'), table_name='deals')
    op.drop_index(op.f('ix_deals_customer_id'), table_name='deals')
    op.drop_index(op.f('ix_deals_agent_id'), table_name='deals')
    op.drop_table('deals')
    op.drop_index(op.f('ix_properties_responsible_id'), table_name='properties')
    op.drop_index(op.f('ix_properties_owner_id'), table_name='properties')
    op.drop_index('ix_properties_match', table_name='properties')
    op.drop_index('ix_properties_features', table_name='properties', postgresql_using='gin')
    op.drop_index('ix_properties_created_at', table_name='properties')
    op.drop_table('properties')
    op.drop_index(op.f('ix_customer_requests_next_follow_up_at'), table_name='customer_requests')
    op.drop_index('ix_customer_requests_match', table_name='customer_requests')
    op.drop_index(op.f('ix_customer_requests_customer_id'), table_name='customer_requests')
    op.drop_index('ix_customer_requests_created_at', table_name='customer_requests')
    op.drop_index(op.f('ix_customer_requests_assigned_agent_id'), table_name='customer_requests')
    op.drop_table('customer_requests')
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_index(op.f('ix_saved_filters_user_id'), table_name='saved_filters')
    op.drop_table('saved_filters')
    op.drop_table('owners')
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_customers_phone_key'), table_name='customers')
    op.drop_index('ix_customers_name_lower', table_name='customers')
    op.drop_index('ix_customers_email_lower', table_name='customers')
    op.drop_index(op.f('ix_customers_assigned_agent_id'), table_name='customers')
    op.drop_table('customers')
    op.drop_index(op.f('ix_auth_tokens_user_id'), table_name='auth_tokens')
    op.drop_table('auth_tokens')
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index('ix_audit_logs_entity', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_table('app_settings')
    op.drop_index('uq_users_email_lower', table_name='users')
    op.drop_table('users')
    op.drop_table('role_permissions')
    op.drop_table('commission_rules')
    op.drop_table('roles')
    op.drop_index('ix_rate_limit_events_key_created', table_name='rate_limit_events')
    op.drop_table('rate_limit_events')
    op.drop_table('property_features')
    op.drop_table('property_categories')
    op.drop_table('permissions')
    op.execute(sa.schema.DropSequence(sa.Sequence('customer_ref_seq')))
    op.execute(sa.schema.DropSequence(sa.Sequence('request_ref_seq')))
    op.execute(sa.schema.DropSequence(sa.Sequence('property_ref_seq')))
    op.execute(sa.schema.DropSequence(sa.Sequence('deal_ref_seq')))
