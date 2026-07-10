#!/usr/bin/env python3
"""
Migración: Crear tablas del módulo Post-Venta
Fecha: 2025-10-30
Descripción: Agrega 11 nuevas tablas sin modificar las existentes
"""

import sys
import os
from pathlib import Path

# Agregar el directorio raíz al path
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from sqlalchemy import create_engine, text, inspect
from app.config import settings
from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

def check_existing_tables(engine):
    """Verifica tablas existentes antes de la migración"""
    inspector = inspect(engine)
    existing = inspector.get_table_names()
    
    logger.info("Tablas existentes antes de migración", count=len(existing))
    
    critical_tables = ['leads', 'conversations']
    for table in critical_tables:
        if table in existing:
            print(f"✅ Tabla crítica encontrada: {table}")
        else:
            print(f"⚠️ Tabla crítica NO encontrada: {table}")
    
    return existing

def upgrade():
    """Crear tablas de post-venta"""
    print("🚀 Iniciando migración de tablas Post-Venta\n")
    
    # Usar SQLite en lugar de PostgreSQL
    engine = create_engine(settings.SQLITE_DATABASE_URL)
    existing_before = check_existing_tables(engine)
    
    print(f"\nTablas existentes: {len(existing_before)}\n")
    
    with engine.connect() as conn:
        try:
            # Tabla 1: sold_packages
            print("Creando tabla: sold_packages...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sold_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER REFERENCES leads(id),
                    package_name VARCHAR(255) NOT NULL,
                    destination_country VARCHAR(100) NOT NULL,
                    destination_cities TEXT,
                    package_type VARCHAR(50),
                    duration_days INTEGER NOT NULL,
                    departure_date DATE NOT NULL,
                    return_date DATE NOT NULL,
                    total_price DECIMAL(10,2) NOT NULL,
                    currency VARCHAR(3) DEFAULT 'USD',
                    payment_status VARCHAR(50),
                    booking_code VARCHAR(50) UNIQUE NOT NULL,
                    passenger_name VARCHAR(100) NOT NULL,
                    passenger_lastname VARCHAR(100) NOT NULL,
                    passenger_email VARCHAR(255) NOT NULL,
                    passenger_phone VARCHAR(50) NOT NULL,
                    passenger_document_type VARCHAR(20),
                    passenger_document_number VARCHAR(50),
                    total_passengers INTEGER DEFAULT 1,
                    trip_status VARCHAR(50) DEFAULT 'confirmed',
                    special_requirements TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sold_by VARCHAR(100)
                )
            """))
            conn.commit()
            print("✅ sold_packages creada\n")
            
            # Tabla 2: package_passengers
            print("Creando tabla: package_passengers...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS package_passengers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id INTEGER REFERENCES sold_packages(id) ON DELETE CASCADE,
                    passenger_type VARCHAR(20),
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    birth_date DATE,
                    gender VARCHAR(10),
                    document_type VARCHAR(20),
                    document_number VARCHAR(50),
                    document_expiry DATE,
                    nationality VARCHAR(50),
                    emergency_contact_name VARCHAR(200),
                    emergency_contact_phone VARCHAR(50),
                    dietary_restrictions TEXT,
                    medical_conditions TEXT,
                    special_assistance TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✅ package_passengers creada\n")
            
            # Tabla 3: package_flights
            print("Creando tabla: package_flights...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS package_flights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id INTEGER REFERENCES sold_packages(id) ON DELETE CASCADE,
                    flight_type VARCHAR(20),
                    flight_sequence INTEGER,
                    airline VARCHAR(100) NOT NULL,
                    flight_number VARCHAR(20) NOT NULL,
                    booking_reference VARCHAR(50),
                    departure_airport_code VARCHAR(10) NOT NULL,
                    departure_airport_name VARCHAR(200),
                    departure_terminal VARCHAR(10),
                    departure_datetime TIMESTAMP NOT NULL,
                    arrival_airport_code VARCHAR(10) NOT NULL,
                    arrival_airport_name VARCHAR(200),
                    arrival_terminal VARCHAR(10),
                    arrival_datetime TIMESTAMP NOT NULL,
                    flight_duration_minutes INTEGER,
                    seat_numbers TEXT,
                    cabin_class VARCHAR(20),
                    baggage_allowance TEXT,
                    checkin_opens_datetime TIMESTAMP,
                    checkin_url TEXT,
                    eticket_url TEXT,
                    voucher_url TEXT,
                    flight_status VARCHAR(50) DEFAULT 'confirmed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✅ package_flights creada\n")
            
            # Tabla 4: package_accommodations
            print("Creando tabla: package_accommodations...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS package_accommodations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id INTEGER REFERENCES sold_packages(id) ON DELETE CASCADE,
                    hotel_name VARCHAR(255) NOT NULL,
                    hotel_category VARCHAR(50),
                    city VARCHAR(100) NOT NULL,
                    address TEXT NOT NULL,
                    postal_code VARCHAR(20),
                    google_maps_url TEXT,
                    coordinates TEXT,
                    hotel_phone VARCHAR(50),
                    hotel_email VARCHAR(255),
                    hotel_website TEXT,
                    booking_confirmation VARCHAR(50) NOT NULL,
                    checkin_date DATE NOT NULL,
                    checkout_date DATE NOT NULL,
                    nights_count INTEGER NOT NULL,
                    room_type VARCHAR(100),
                    room_number VARCHAR(20),
                    bed_configuration VARCHAR(100),
                    meal_plan VARCHAR(50),
                    amenities TEXT,
                    checkin_time TIME,
                    checkout_time TIME,
                    early_checkin_available BOOLEAN DEFAULT 0,
                    late_checkout_available BOOLEAN DEFAULT 0,
                    voucher_url TEXT,
                    hotel_policies_url TEXT,
                    special_requests TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✅ package_accommodations creada\n")
            
            # Tabla 5: package_transfers
            print("Creando tabla: package_transfers...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS package_transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id INTEGER REFERENCES sold_packages(id) ON DELETE CASCADE,
                    transfer_type VARCHAR(50) NOT NULL,
                    transfer_sequence INTEGER,
                    transfer_date DATE NOT NULL,
                    pickup_time TIME NOT NULL,
                    estimated_arrival_time TIME,
                    pickup_location VARCHAR(255) NOT NULL,
                    pickup_address TEXT,
                    pickup_instructions TEXT,
                    dropoff_location VARCHAR(255) NOT NULL,
                    dropoff_address TEXT,
                    provider_name VARCHAR(200),
                    provider_phone VARCHAR(50),
                    driver_name VARCHAR(200),
                    driver_phone VARCHAR(50),
                    vehicle_type VARCHAR(100),
                    vehicle_plate VARCHAR(20),
                    vehicle_capacity INTEGER,
                    booking_reference VARCHAR(50),
                    voucher_url TEXT,
                    notes TEXT,
                    transfer_status VARCHAR(50) DEFAULT 'confirmed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✅ package_transfers creada\n")
            
            # Tabla 6: package_activities
            print("Creando tabla: package_activities...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS package_activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id INTEGER REFERENCES sold_packages(id) ON DELETE CASCADE,
                    activity_name VARCHAR(255) NOT NULL,
                    activity_type VARCHAR(100),
                    city VARCHAR(100),
                    activity_date DATE NOT NULL,
                    start_time TIME,
                    end_time TIME,
                    duration_hours DECIMAL(4,2),
                    meeting_point VARCHAR(255),
                    meeting_point_address TEXT,
                    meeting_point_instructions TEXT,
                    meeting_point_maps_url TEXT,
                    provider_name VARCHAR(200),
                    provider_phone VARCHAR(50),
                    guide_name VARCHAR(200),
                    guide_phone VARCHAR(50),
                    description TEXT,
                    included_services TEXT,
                    not_included TEXT,
                    what_to_bring TEXT,
                    booking_reference VARCHAR(50),
                    voucher_url TEXT,
                    price_per_person DECIMAL(10,2),
                    notes TEXT,
                    activity_status VARCHAR(50) DEFAULT 'confirmed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✅ package_activities creada\n")
            
            # Tabla 7: package_documents
            print("Creando tabla: package_documents...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS package_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id INTEGER REFERENCES sold_packages(id) ON DELETE CASCADE,
                    document_type VARCHAR(50) NOT NULL,
                    related_to VARCHAR(50),
                    related_id INTEGER,
                    document_name VARCHAR(255) NOT NULL,
                    document_description TEXT,
                    file_url TEXT NOT NULL,
                    file_type VARCHAR(20),
                    file_size_kb INTEGER,
                    issue_date DATE,
                    expiry_date DATE,
                    document_number VARCHAR(100),
                    is_required BOOLEAN DEFAULT 0,
                    is_printable BOOLEAN DEFAULT 1,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✅ package_documents creada\n")
            
            # Tabla 8: package_itinerary
            print("Creando tabla: package_itinerary...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS package_itinerary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id INTEGER REFERENCES sold_packages(id) ON DELETE CASCADE,
                    day_number INTEGER NOT NULL,
                    itinerary_date DATE NOT NULL,
                    day_title VARCHAR(255),
                    city VARCHAR(100),
                    morning_activities TEXT,
                    afternoon_activities TEXT,
                    evening_activities TEXT,
                    breakfast_included BOOLEAN DEFAULT 0,
                    lunch_included BOOLEAN DEFAULT 0,
                    dinner_included BOOLEAN DEFAULT 0,
                    accommodation_id INTEGER REFERENCES package_accommodations(id),
                    notes TEXT,
                    tips TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✅ package_itinerary creada\n")
            
            # Tabla 9: support_tickets
            print("Creando tabla: support_tickets...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_id INTEGER REFERENCES sold_packages(id) ON DELETE CASCADE,
                    ticket_number VARCHAR(50) UNIQUE NOT NULL,
                    ticket_subject VARCHAR(255) NOT NULL,
                    ticket_category VARCHAR(100),
                    priority VARCHAR(20) DEFAULT 'medium',
                    status VARCHAR(50) DEFAULT 'open',
                    description TEXT NOT NULL,
                    passenger_location VARCHAR(255),
                    assigned_to VARCHAR(100),
                    assigned_at TIMESTAMP,
                    resolution TEXT,
                    resolved_at TIMESTAMP,
                    resolution_type VARCHAR(50),
                    auto_resolved_by_agent BOOLEAN DEFAULT 0,
                    resolution_time_minutes INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    related_flight_id INTEGER REFERENCES package_flights(id),
                    related_hotel_id INTEGER REFERENCES package_accommodations(id),
                    related_transfer_id INTEGER REFERENCES package_transfers(id),
                    related_activity_id INTEGER REFERENCES package_activities(id)
                )
            """))
            conn.commit()
            print("✅ support_tickets creada\n")
            
            # Tabla 10: ticket_interactions
            print("Creando tabla: ticket_interactions...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ticket_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER REFERENCES support_tickets(id) ON DELETE CASCADE,
                    interaction_type VARCHAR(50),
                    message TEXT NOT NULL,
                    created_by VARCHAR(100),
                    attachments TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    channel VARCHAR(50)
                )
            """))
            conn.commit()
            print("✅ ticket_interactions creada\n")
            
            # Tabla 11: postsale_sessions
            print("Creando tabla: postsale_sessions...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS postsale_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    package_id INTEGER REFERENCES sold_packages(id),
                    validated_at TIMESTAMP,
                    validation_method VARCHAR(50),
                    last_interaction TIMESTAMP,
                    total_messages INTEGER DEFAULT 0,
                    tickets_created INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✅ postsale_sessions creada\n")
            
            # Verificar que tablas críticas siguen intactas
            inspector = inspect(engine)
            existing_after = inspector.get_table_names()
            
            print("="*60)
            print("VERIFICANDO TABLAS CRÍTICAS...")
            print("="*60)
            
            critical_tables = ['leads', 'conversations']
            all_critical_ok = True
            for table in critical_tables:
                if table in existing_after:
                    print(f"✅ Tabla crítica verificada: {table}")
                else:
                    print(f"❌ ERROR: Tabla crítica perdida: {table}")
                    all_critical_ok = False
            
            print("\n" + "="*60)
            print("✅ MIGRACIÓN COMPLETADA EXITOSAMENTE")
            print("="*60)
            print(f"Tablas antes: {len(existing_before)}")
            print(f"Tablas después: {len(existing_after)}")
            print(f"Tablas nuevas: {len(existing_after) - len(existing_before)}")
            print("="*60 + "\n")
            
            if not all_critical_ok:
                raise Exception("ERROR: Se perdieron tablas críticas durante la migración")
            
        except Exception as e:
            print(f"\n❌ ERROR en migración: {str(e)}\n")
            conn.rollback()
            raise

if __name__ == "__main__":
    upgrade()