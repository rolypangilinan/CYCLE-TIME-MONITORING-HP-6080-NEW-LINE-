# Cycle Time Monitoring System

This is a Flask-based web application for monitoring cycle times across 9 production processes with MariaDB database integration.

## Features

- Real-time cycle time monitoring for 9 processes
- Database logging of all process events (START, STOP, NG, LINEOUT)
- Line-out reason tracking with predefined and custom reasons
- Kitting number tracking
- Pass/Fail status recording

## Database Schema

The `process_records` table stores all process events with the following columns:

- `id` (INT AUTO_INCREMENT PRIMARY KEY): Unique record identifier
- `kitting_no` (VARCHAR 255): Kitting number from the dashboard
- `lineout_reason` (VARCHAR 255): Selected line-out reason (null for non-lineout events)
- `elapsed_time` (TIME): Process duration in MM:SS format
- `pass_ng` (INTEGER): Pass (1) or Fail (0) status
- `timestamp` (DATETIME): Automatic timestamp of record creation
- `process_no` (INTEGER): Process number (1-9)

## Setup Instructions

### Prerequisites

1. XAMPP with MariaDB installed and running
2. Python 3.7 or higher
3. pip (Python package manager)

### Installation Steps

1. **Install Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start MariaDB in XAMPP**
   - Open XAMPP Control Panel
   - Start the MySQL/MariaDB service
   - Ensure it's running on port 3306

3. **Run the Application**
   ```bash
   python cycleTimeMoni.py
   ```

   The application will:
   - Automatically create the database `cycle_time_monitoring` if it doesn't exist
   - Create the `process_records` table with the required schema
   - Start the Flask server on http://localhost:5000

### Database Configuration

The default database configuration in `database_manager.py`:
- Host: localhost
- Port: 3306
- User: root
- Password: (empty - default XAMPP)
- Database: cycle_time_monitoring

If you need to change these settings, modify the `DatabaseManager` class in `database_manager.py`.

## Usage

1. Open your web browser and go to http://localhost:5000
2. Navigate to any process page (Process 1-9)
3. Use the control buttons:
   - **START**: Begins a new cycle with a new kitting number
   - **STOP**: Ends the current cycle and records the elapsed time
   - **NG**: Marks the current cycle as failed (No Good)
   - **LINEOUT**: Opens a modal to select a line-out reason

All events are automatically logged to the database with timestamps.

## API Endpoints

The application provides the following REST API endpoints:

- `POST /api/start_process` - Log a START event
- `POST /api/stop_process` - Log a STOP event
- `POST /api/ng_process` - Log an NG event
- `POST /api/lineout_process` - Log a LINEOUT event with reason
- `GET /api/get_process_records/<process_no>` - Get records for a specific process

## Troubleshooting

### Database Connection Issues

If you get a database connection error:

1. Ensure MariaDB is running in XAMPP
2. Check that the port 3306 is not blocked
3. Verify the database credentials in `database_manager.py`
4. Try accessing phpMyAdmin to confirm MariaDB is working

### Missing Dependencies

If you get import errors:

```bash
pip install -r requirements.txt
```

### Port Already in Use

If port 5000 is already in use, you can change it in `cycleTimeMoni.py`:

```python
app.run(host="0.0.0.0", port=5001, debug=True)
```

## Data Management

To view the stored data:

1. Open phpMyAdmin from XAMPP
2. Select the `cycle_time_monitoring` database
3. Browse the `process_records` table

You can export data from phpMyAdmin in various formats (CSV, Excel, SQL) for analysis.
