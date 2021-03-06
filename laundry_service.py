import RPi.GPIO as GPIO
import time
import requests


class Laundry:
    def __init__(self, machine_type: str, machine_id: str):
        GPIO.setmode(GPIO.BOARD)
        # set pin 40 or GPIO21 as the input/output
        self._pin_to_circuit=40 # GPIO pin to circuit
        self._raw_light = 0 # raw value of LDR
        self._weighted_average = 300 # the brightness benchmark
        self._bool_status = False # False if dark (FINISHED) ; True if bright (STARTED)
        self._machine_type = machine_type # dryer of wmachine
        self._machine_id = machine_id # unique id in db as a string
        self._base_url="http://ec2-54-180-114-209.ap-northeast-2.compute.amazonaws.com:8080" # URL for database
        self._time_count = 30 # counter to update over this many cycles
        self._request_backlog = [] #stores list of requests that could not be completed
        self._maintenance_pin = 38
        GPIO.setup(self._maintenance_pin, GPIO.IN) #setup pin 38 to be the maintenance detector

    def rc_time (self):
        # RPI doesn't have any analog pins so we need to use the time it takes
        # to charge the capacitor instead to measure analog values
        _count = 0
        # output low voltage on GPIO pin
        GPIO.setup(self._pin_to_circuit, GPIO.OUT)
        GPIO.output(self._pin_to_circuit, GPIO.LOW)
        time.sleep(0.1)
        # change the pin back to input
        GPIO.setup(self._pin_to_circuit, GPIO.IN)
        #increment count until the pin goes high
        while (GPIO.input(self._pin_to_circuit) == GPIO.LOW):
            _count += 1
        self._raw_light = _count
        
    def calculate_wma(self):
        # use a weighted average to smooth the readings
        # here we use an alpha value of 0.125
        _tmp_weighted_average = 0.875*self._weighted_average + 0.125*self._raw_light
        self._weighted_average = _tmp_weighted_average
        # set the status
        self._bool_status =  _tmp_weighted_average >= 300

    def queue_send_status(self):
        # build the request string
        request_string = self._base_url + "/api/" + self._machine_type + "/" + self._machine_id + "/event"
        # get unix epoch time and status string for JSON
        timestamp_string = str(int(time.time()))
        status_string = None
        if GPIO.input(self._maintenance_pin) == GPIO.HIGH: 
            status_string = "MAINTENANCE"
        elif self._bool_status == True:
            status_string = "STARTED"
        else:
            status_string = "FINISHED"
        tmp_json = {"timestamp": timestamp_string, "status": status_string}
        # make request
        print("queueing request with url: " + request_string )
        print("and json = {timestamp: " + timestamp_string + ", status: " + status_string + "}")

        self._request_backlog.insert(0, (request_string, tmp_json))

        """
        try:
            r = requests.post(request_string, json=tmp_json)
            r.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            print("http error")
        except requests.exceptions.ConnectionError as errc:
            print("connection error")
        except requests.exceptions.TimeoutError as errt:
            print("timeout error")
        except requests.exceptions.RequestException as err:
            print("requestexception error")
        """

    def clear_backlog(self):
        for req_tup in self._request_backlog:
            try:
                r = requests.post(req_tup[0], json=req_tup[1], timeout=5)
                if r.ok:
                    print("request sent for ", req_tup[1])
                    self._request_backlog.pop(0)
                r.raise_for_status()
            except requests.exceptions.HTTPError as errh:
                print("http error", req_tup[1])
            except requests.exceptions.ConnectionError as errc:
                print("connection error", req_tup[1])
            except requests.exceptions.Timeout as errt:
                print("timeout error", req_tup[1])
            except requests.exceptions.RequestException as err:
                print("requestexception error", req_tup[1])
            

    def run(self):
        try:
            # Main loop
            while True:
                # get readings from LDR continuously
                time.sleep(0.5)
                self.rc_time()
                self.calculate_wma()
                #print(self._weighted_average)
                print(self._bool_status, int(self._weighted_average)) 
                self._time_count-=1
                # update database every few cycles
                if self._time_count <= 0:
                    self.queue_send_status()
                    self.clear_backlog()
                    self._time_count=30
        #catch when script is interrupted, cleanup correctly
        except KeyboardInterrupt:
            pass
        finally:
            GPIO.cleanup()

laundry = Laundry("dryer", "10")
laundry.run()
