CREATE TABLE IF NOT EXISTS "Client" (
    id SERIAL PRIMARY KEY,
    emailaddress VARCHAR(255) UNIQUE NOT NULL,
    "Name" VARCHAR(255),
    "Lastname" VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "Companies" (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    emailaddress VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "Drivers" (
    id SERIAL PRIMARY KEY,
    email_address VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    company_id INTEGER REFERENCES "Companies"(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS "Address" (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES "Client"(id) ON DELETE CASCADE,
    street_name VARCHAR(255) NOT NULL,
    house_number VARCHAR(50) NOT NULL,
    city VARCHAR(255) NOT NULL,
    phone_number VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE IF NOT EXISTS "Orders" (
    id SERIAL PRIMARY KEY,
    deadline DATE,
    task_type_id INTEGER,
    product_type VARCHAR(255),
    "Weight" DECIMAL(10, 2),
    address_id INTEGER NOT NULL,
    driver_id INTEGER,
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'completed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT Orders_task_type_id_fkey FOREIGN KEY (task_type_id) REFERENCES "TaskTypes"(id) ON DELETE RESTRICT,
    CONSTRAINT orders_address_id_fkey FOREIGN KEY (address_id) REFERENCES "Address"(id) ON DELETE RESTRICT,
    CONSTRAINT Orders_driver_id_fkey FOREIGN KEY (driver_id) REFERENCES "Drivers"(id) ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS "TaskTypes" (
    id SERIAL PRIMARY KEY,
    task_type VARCHAR(255) NOT NULL,
    company_id INTEGER NOT NULL REFERENCES "Companies"(id) ON DELETE CASCADE,
    time_per_1000kg DECIMAL(10, 4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_client_emailaddress ON "Client"(emailaddress);
CREATE INDEX IF NOT EXISTS idx_companies_emailaddress ON "Companies"(emailaddress);
CREATE INDEX IF NOT EXISTS idx_drivers_email_address ON "Drivers"(email_address);
CREATE INDEX IF NOT EXISTS idx_drivers_company_id ON "Drivers"(company_id);
CREATE INDEX IF NOT EXISTS idx_address_client_id ON "Address"(client_id);
CREATE INDEX IF NOT EXISTS idx_orders_address_id ON "Orders"(address_id);
CREATE INDEX IF NOT EXISTS idx_orders_task_type_id ON "Orders"(task_type_id);
CREATE INDEX IF NOT EXISTS idx_orders_driver_id ON "Orders"(driver_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON "Orders"(status);
CREATE INDEX IF NOT EXISTS idx_orders_deadline ON "Orders"(deadline);
CREATE INDEX IF NOT EXISTS idx_tasktypes_company_id ON "TaskTypes"(company_id);


COMMENT ON TABLE "Client" IS 'Stores customer (klant) information';
COMMENT ON TABLE "Companies" IS 'Stores company/service provider (bedrijf) information';
COMMENT ON TABLE "Drivers" IS 'Stores driver (chauffeur) information linked to companies';
COMMENT ON TABLE "Address" IS 'Stores customer addresses';
COMMENT ON TABLE "Orders" IS 'Stores customer orders/bookings with status tracking';
COMMENT ON TABLE "TaskTypes" IS 'Stores task types per company with time per 1000kg';


COMMENT ON COLUMN "Orders".status IS 'Order status: pending, accepted, or completed';
COMMENT ON COLUMN "Orders"."Weight" IS 'Weight in kg';
COMMENT ON COLUMN "Orders".deadline IS 'Deadline date for order completion';
COMMENT ON COLUMN "Orders".task_type_id IS 'Foreign key to TaskTypes table, links to company via TaskTypes.company_id';
COMMENT ON COLUMN "Drivers".company_id IS 'Foreign key to Companies table, nullable for drivers without company';
COMMENT ON COLUMN "TaskTypes".task_type IS 'Name of the task type (e.g., ploegen, pletten)';
COMMENT ON COLUMN "TaskTypes".company_id IS 'Foreign key to Companies table';
COMMENT ON COLUMN "TaskTypes".time_per_1000kg IS 'Time in hours needed per 1000kg for this task type';

