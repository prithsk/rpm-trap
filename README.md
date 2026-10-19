# rpm-trap

Does chasing the highest rate per mile cost truck drivers money?

A load with a great rate per mile can end in a city with nothing to haul out, and the empty miles to the next pickup pay nothing. This benchmark simulates real weeks of refrigerated freight on the USDA's public weekly lane rates and compares three ways to pick loads with the same weekly mileage:

1. **Highest loaded RPM nearby.** Take the best-paying load per loaded mile within 250 empty miles.
2. **Highest all-in RPM.** Count the empty miles to reach the pickup, one load at a time.
3. **Plan the week.** Find the best chain of loads for the whole week, exactly, by dynamic programming over the mileage budget.

## Results

<!-- results:start -->
_Run it to populate._
<!-- results:end -->

## Data

[USDA AgTransport: Refrigerated Truck Rates and Availability](https://agtransport.usda.gov/Truck/Refrigerated-Truck-Rates-and-Availability/acar-e3r8), compiled from the weekly AMS Specialty Crops Fruit and Vegetable Truck Rate Report: spot rates per load from produce shipping districts to ten receiving cities, with USDA's own distance and rate per mile. Public, no key needed.

## Calibration

USDA publishes its own rate per mile for every row. The benchmark recomputes it from the rate range and distance and reports the median error, so a parsing mistake shows up before any comparison does.

## Run it

```
python test_bench.py
python bench.py                 # last 52 weeks, 2,750 miles a week, 250-mile radius for the RPM rule
python bench.py --radius 150    # how sensitive the result is to the radius
```

Standard library only. Python 3.9 or newer.

## How the planner works

After each load the truck sits in one of ten destination cities, so the state is the city plus miles left in the week. The best revenue from each state is computed bottom-up over 25-mile steps, rounding every leg up so a plan never overspends its miles. A brute-force test over every chain of loads confirms it's exact.

## License

MIT
