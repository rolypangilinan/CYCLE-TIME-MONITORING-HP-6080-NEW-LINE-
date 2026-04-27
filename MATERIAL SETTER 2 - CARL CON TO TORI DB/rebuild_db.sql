USE cycle_time_monitoring;

-- Create process_records table
CREATE TABLE IF NOT EXISTS process_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kitting_no VARCHAR(255),
    lineout_reason VARCHAR(255),
    in_line_reason VARCHAR(255),
    repaired_action VARCHAR(255),
    elapsed_time TIME,
    pass_ng INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_no INTEGER,
    INDEX idx_process_no (process_no),
    INDEX idx_timestamp (timestamp)
);

-- Create standard_times table
CREATE TABLE IF NOT EXISTS standard_times (
    process_no INT PRIMARY KEY,
    standard_time DECIMAL(5,2) DEFAULT 1.50,
    title VARCHAR(255) DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Insert default standard times
INSERT INTO standard_times (process_no, standard_time, title) VALUES
(1, 1.56, 'EM Fastening'),
(2, 1.73, 'DF & Rod Casing Fastening'),
(3, 1.53, 'Partition Board'),
(4, 1.49, 'Lower Housing Prep'),
(5, 1.46, 'Lower Housing Fastening'),
(6, 1.50, 'Combination Leadwire Arrange'),
(7, 0.70, 'Soldering'),
(8, 1.18, 'Upper Housing'),
(9, 1.44, 'Packing');

-- Create manpower table
CREATE TABLE IF NOT EXISTS manpower (
    process_no INT PRIMARY KEY,
    id_no VARCHAR(50) DEFAULT '',
    operator_name VARCHAR(255) DEFAULT '',
    employment_status VARCHAR(50) DEFAULT '',
    operator_manual VARCHAR(255) DEFAULT '',
    operator_scan VARCHAR(255) DEFAULT '',
    time_in DATETIME DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Insert default manpower rows
INSERT INTO manpower (process_no) VALUES (1), (2), (3), (4), (5), (6), (7), (8), (9);

-- Create bio_break table
CREATE TABLE IF NOT EXISTS bio_break (
    id INT AUTO_INCREMENT PRIMARY KEY,
    out_reasons VARCHAR(255) NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Insert default OUT reasons
INSERT INTO bio_break (out_reasons) VALUES ('CR'), ('CLINIC'), ('GO TO OTHER LINE'), ('EMERGENCY'), ('SENT HOME');

-- Create lineout_reasons table
CREATE TABLE IF NOT EXISTS lineout_reasons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reason VARCHAR(255) NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Insert default LINE OUT reasons
INSERT INTO lineout_reasons (reason) VALUES ('NG PRESSURE'), ('LEAK'), ('LW'), ('LAV'), ('LCP'), ('LA'), ('HW'), ('HAV'), ('HCP'), ('HA');

-- Create in_line_reasons table
CREATE TABLE IF NOT EXISTS in_line_reasons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reason VARCHAR(255) NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create repaired_actions table
CREATE TABLE IF NOT EXISTS repaired_actions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reason VARCHAR(255) NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create process_1 table
CREATE TABLE IF NOT EXISTS process_1 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kitting_no VARCHAR(255),
    lineout_reason VARCHAR(255),
    in_line_reason VARCHAR(255),
    repaired_action VARCHAR(255),
    elapsed_time TIME,
    pass_ng INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_no INTEGER,
    operator_name VARCHAR(255) DEFAULT '',
    time_in DATETIME DEFAULT NULL,
    time_out DATETIME DEFAULT NULL,
    out_reasons VARCHAR(255) DEFAULT '',
    INDEX idx_timestamp (timestamp)
);

-- Create process_2 table
CREATE TABLE IF NOT EXISTS process_2 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kitting_no VARCHAR(255),
    lineout_reason VARCHAR(255),
    in_line_reason VARCHAR(255),
    repaired_action VARCHAR(255),
    elapsed_time TIME,
    pass_ng INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_no INTEGER,
    operator_name VARCHAR(255) DEFAULT '',
    time_in DATETIME DEFAULT NULL,
    time_out DATETIME DEFAULT NULL,
    out_reasons VARCHAR(255) DEFAULT '',
    INDEX idx_timestamp (timestamp)
);

-- Create process_3 table
CREATE TABLE IF NOT EXISTS process_3 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kitting_no VARCHAR(255),
    lineout_reason VARCHAR(255),
    in_line_reason VARCHAR(255),
    repaired_action VARCHAR(255),
    elapsed_time TIME,
    pass_ng INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_no INTEGER,
    operator_name VARCHAR(255) DEFAULT '',
    time_in DATETIME DEFAULT NULL,
    time_out DATETIME DEFAULT NULL,
    out_reasons VARCHAR(255) DEFAULT '',
    INDEX idx_timestamp (timestamp)
);

-- Create process_4 table
CREATE TABLE IF NOT EXISTS process_4 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kitting_no VARCHAR(255),
    lineout_reason VARCHAR(255),
    in_line_reason VARCHAR(255),
    repaired_action VARCHAR(255),
    elapsed_time TIME,
    pass_ng INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_no INTEGER,
    operator_name VARCHAR(255) DEFAULT '',
    time_in DATETIME DEFAULT NULL,
    time_out DATETIME DEFAULT NULL,
    out_reasons VARCHAR(255) DEFAULT '',
    INDEX idx_timestamp (timestamp)
);

-- Create process_5 table
CREATE TABLE IF NOT EXISTS process_5 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kitting_no VARCHAR(255),
    lineout_reason VARCHAR(255),
    in_line_reason VARCHAR(255),
    repaired_action VARCHAR(255),
    elapsed_time TIME,
    pass_ng INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_no INTEGER,
    operator_name VARCHAR(255) DEFAULT '',
    time_in DATETIME DEFAULT NULL,
    time_out DATETIME DEFAULT NULL,
    out_reasons VARCHAR(255) DEFAULT '',
    INDEX idx_timestamp (timestamp)
);

-- Create process_6 table
CREATE TABLE IF NOT EXISTS process_6 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kitting_no VARCHAR(255),
    lineout_reason VARCHAR(255),
    in_line_reason VARCHAR(255),
    repaired_action VARCHAR(255),
    elapsed_time TIME,
    pass_ng INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_no INTEGER,
    operator_name VARCHAR(255) DEFAULT '',
    time_in DATETIME DEFAULT NULL,
    time_out DATETIME DEFAULT NULL,
    out_reasons VARCHAR(255) DEFAULT '',
    INDEX idx_timestamp (timestamp)
);

-- Create process_7 table
CREATE TABLE IF NOT EXISTS process_7 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kitting_no VARCHAR(255),
    lineout_reason VARCHAR(255),
    in_line_reason VARCHAR(255),
    repaired_action VARCHAR(255),
    elapsed_time TIME,
    pass_ng INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_no INTEGER,
    operator_name VARCHAR(255) DEFAULT '',
    time_in DATETIME DEFAULT NULL,
    time_out DATETIME DEFAULT NULL,
    out_reasons VARCHAR(255) DEFAULT '',
    INDEX idx_timestamp (timestamp)
);

-- Create process_8 table
CREATE TABLE IF NOT EXISTS process_8 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kitting_no VARCHAR(255),
    lineout_reason VARCHAR(255),
    in_line_reason VARCHAR(255),
    repaired_action VARCHAR(255),
    elapsed_time TIME,
    pass_ng INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_no INTEGER,
    operator_name VARCHAR(255) DEFAULT '',
    time_in DATETIME DEFAULT NULL,
    time_out DATETIME DEFAULT NULL,
    out_reasons VARCHAR(255) DEFAULT '',
    INDEX idx_timestamp (timestamp)
);

-- Create process_9 table
CREATE TABLE IF NOT EXISTS process_9 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    kitting_no VARCHAR(255),
    lineout_reason VARCHAR(255),
    in_line_reason VARCHAR(255),
    repaired_action VARCHAR(255),
    elapsed_time TIME,
    pass_ng INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    process_no INTEGER,
    operator_name VARCHAR(255) DEFAULT '',
    time_in DATETIME DEFAULT NULL,
    time_out DATETIME DEFAULT NULL,
    out_reasons VARCHAR(255) DEFAULT '',
    INDEX idx_timestamp (timestamp)
);
