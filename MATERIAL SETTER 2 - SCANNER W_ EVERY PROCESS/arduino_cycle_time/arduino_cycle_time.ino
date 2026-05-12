/*
  Cycle Time Monitoring - Arduino Button Controller
  ==================================================
  Reads physical buttons for 9 processes (START/STOP each).
  Sends serial messages to the computer when a button is pressed.

  Pin Mapping:
  -----------------------------------------------
  Process 1: START=41, STOP=42
  Process 2: START=43, STOP=44
  Process 3: START=45, STOP=46
  Process 4: START=47, STOP=48
  Process 5: START=49, STOP=50
  Process 6: START=3,  STOP=4
  Process 7: START=5,  STOP=6
  Process 8: START=7,  STOP=8
  Process 9: START=9,  STOP=10
  -----------------------------------------------

  Wiring: Each button connects the pin to GND.
  Internal pull-up resistors are used (LOW = pressed).

  Serial Output Examples:
    P1START, P1STOP, P2START, P2STOP, ... P9START, P9STOP
*/

// Number of processes
const int NUM_PROCESSES = 9;

// Pin arrays: index 0 = Process 1, index 8 = Process 9
const int startPins[NUM_PROCESSES] = {41, 43, 45, 47, 49, 3, 5, 7, 9};
const int stopPins[NUM_PROCESSES]  = {42, 44, 46, 48, 50, 4, 6, 8, 10};

// Previous button states for edge detection (HIGH = not pressed due to pull-up)
bool prevStartState[NUM_PROCESSES];
bool prevStopState[NUM_PROCESSES];

// Debounce timing
unsigned long lastStartDebounce[NUM_PROCESSES];
unsigned long lastStopDebounce[NUM_PROCESSES];
const unsigned long DEBOUNCE_DELAY = 50; // 50ms debounce

void setup() {
  // Start serial communication at 9600 baud
  Serial.begin(9600);

  for (int i = 0; i < NUM_PROCESSES; i++) {
    // Set all button pins as INPUT with internal pull-up resistor
    // When button is NOT pressed, pin reads HIGH
    // When button IS pressed (connected to GND), pin reads LOW
    pinMode(startPins[i], INPUT_PULLUP);
    pinMode(stopPins[i], INPUT_PULLUP);

    // Initialize previous states as HIGH (not pressed)
    prevStartState[i] = HIGH;
    prevStopState[i] = HIGH;

    // Initialize debounce timers
    lastStartDebounce[i] = 0;
    lastStopDebounce[i] = 0;
  }

  Serial.println("ARDUINO_READY");
}

void loop() {
  unsigned long currentTime = millis();

  for (int i = 0; i < NUM_PROCESSES; i++) {
    // --- Read START button ---
    bool currentStartState = digitalRead(startPins[i]);

    // Detect falling edge (HIGH -> LOW) = button just pressed
    if (currentStartState == LOW && prevStartState[i] == HIGH) {
      if ((currentTime - lastStartDebounce[i]) > DEBOUNCE_DELAY) {
        lastStartDebounce[i] = currentTime;

        // Send START signal for this process
        Serial.print("P");
        Serial.print(i + 1);
        Serial.println("START");
      }
    }
    prevStartState[i] = currentStartState;

    // --- Read STOP button ---
    bool currentStopState = digitalRead(stopPins[i]);

    // Detect falling edge (HIGH -> LOW) = button just pressed
    if (currentStopState == LOW && prevStopState[i] == HIGH) {
      if ((currentTime - lastStopDebounce[i]) > DEBOUNCE_DELAY) {
        lastStopDebounce[i] = currentTime;

        // Send STOP signal for this process
        Serial.print("P");
        Serial.print(i + 1);
        Serial.println("STOP");
      }
    }
    prevStopState[i] = currentStopState;
  }

  // Small delay to prevent excessive CPU usage
  delay(5);
}
