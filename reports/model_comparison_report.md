# AssureX Dual-Model Consensus Evaluation Report

Official verification dossier comparing Python Tabular Classifier vs. Google Teachable Machine Vision Classifier on unseen test data.

## Executive Summary

- **Evaluated Test Claims:** 36
- **Dual-Model Class Agreement Rate:** 100.00%
- **Average Confidence Difference (|Δconf|):** 0.0088

### Consistency Status Distribution

| Model Consistency Status | Claim Count | Share (%) |
|:---|:---:|:---:|
| **Strong Match** | 36 | 100.0% |
| **Acceptable Match** | 0 | 0.0% |
| **Weak Match** | 0 | 0.0% |
| **Model Disagreement** | 0 | 0.0% |
| **Uncertain Result** | 0 | 0.0% |

## Detailed Claim-by-Claim Adjudication Log (21-Column Schema)

| Claim ID | Category | Fault Category | Python Pred | Py Conf | GTM Pred | GTM Conf | Class Match | |Δconf| | Consistency Status | Final Decision |
|:---|:---|:---|:---|:---:|:---|:---:|:---:|:---:|:---|:---|
| `CLM-00805` | Consumer Electronics | Third-party unauthorized disassembly | Invalid Claim | 0.9678 | Invalid Claim | 1.0000 | ✅ Yes | 0.0322 | `Strong Match` | **Likely Invalid** |
| `CLM-00672` | Industrial & Automotive Tools | Normal consumable wear (brushes, chuck teeth) | Invalid Claim | 0.9998 | Invalid Claim | 1.0000 | ✅ Yes | 0.0002 | `Strong Match` | **Manual Review Required** |
| `CLM-00656` | Home Appliances | Third-party modifications | Invalid Claim | 0.9998 | Invalid Claim | 1.0000 | ✅ Yes | 0.0002 | `Strong Match` | **Likely Invalid** |
| `CLM-00541` | Home Appliances | Third-party modifications | Invalid Claim | 0.9952 | Invalid Claim | 1.0000 | ✅ Yes | 0.0048 | `Strong Match` | **Likely Invalid** |
| `CLM-00625` | Home Appliances | Drum spin malfunction | Invalid Claim | 0.9927 | Invalid Claim | 1.0000 | ✅ Yes | 0.0073 | `Strong Match` | **Manual Review Required** |
| `CLM-00531` | Industrial & Automotive Tools | Gearbox seizure | Invalid Claim | 1.0000 | Invalid Claim | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Manual Review Required** |
| `CLM-00545` | Home Appliances | Commercial heavy utilization | Invalid Claim | 0.9998 | Invalid Claim | 1.0000 | ✅ Yes | 0.0002 | `Strong Match` | **Likely Invalid** |
| `CLM-00839` | Industrial & Automotive Tools | Armature burning | Invalid Claim | 1.0000 | Invalid Claim | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Manual Review Required** |
| `CLM-00996` | Industrial & Automotive Tools | Abnormal overload beyond specified torque limits | Invalid Claim | 0.9920 | Invalid Claim | 1.0000 | ✅ Yes | 0.0080 | `Strong Match` | **Likely Invalid** |
| `CLM-00829` | Consumer Electronics | Power surge overvoltage | Invalid Claim | 0.9906 | Invalid Claim | 1.0000 | ✅ Yes | 0.0094 | `Strong Match` | **Likely Invalid** |
| `CLM-00936` | Home Appliances | Water pump leakage | Invalid Claim | 1.0000 | Invalid Claim | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Manual Review Required** |
| `CLM-00840` | Industrial & Automotive Tools | Trigger switch failure | Invalid Claim | 0.9778 | Invalid Claim | 1.0000 | ✅ Yes | 0.0222 | `Strong Match` | **Manual Review Required** |
| `CLM-00774` | Consumer Electronics | Battery failure to charge | Invalid Claim | 0.9903 | Invalid Claim | 1.0000 | ✅ Yes | 0.0097 | `Strong Match` | **Manual Review Required** |
| `CLM-01419` | Industrial & Automotive Tools | Chuck bearing breakdown | Manual Review | 0.9875 | Manual Review | 1.0000 | ✅ Yes | 0.0125 | `Strong Match` | **Manual Review Required** |
| `CLM-01284` | Consumer Electronics | Screen flickering | Manual Review | 1.0000 | Manual Review | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Manual Review Required** |
| `CLM-01017` | Consumer Electronics | Bluetooth/Wi-Fi failure | Manual Review | 1.0000 | Manual Review | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Manual Review Required** |
| `CLM-01148` | Consumer Electronics | Bluetooth/Wi-Fi failure | Manual Review | 1.0000 | Manual Review | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Manual Review Required** |
| `CLM-01043` | Consumer Electronics | Screen flickering | Manual Review | 1.0000 | Manual Review | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Manual Review Required** |
| `CLM-01186` | Home Appliances | Thermostat failure | Manual Review | 0.9827 | Manual Review | 1.0000 | ✅ Yes | 0.0173 | `Strong Match` | **Manual Review Required** |
| `CLM-01440` | Home Appliances | Water pump leakage | Manual Review | 1.0000 | Manual Review | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Manual Review Required** |
| `CLM-01084` | Consumer Electronics | Screen flickering | Manual Review | 1.0000 | Manual Review | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Manual Review Required** |
| `CLM-01099` | Home Appliances | Water pump leakage | Manual Review | 0.9938 | Manual Review | 1.0000 | ✅ Yes | 0.0062 | `Strong Match` | **Manual Review Required** |
| `CLM-01167` | Industrial & Automotive Tools | Armature burning | Manual Review | 1.0000 | Manual Review | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Manual Review Required** |
| `CLM-01039` | Consumer Electronics | Speaker malfunction | Manual Review | 0.9157 | Manual Review | 1.0000 | ✅ Yes | 0.0843 | `Strong Match` | **Manual Review Required** |
| `CLM-01218` | Consumer Electronics | Unresponsive touch panel | Manual Review | 0.9425 | Manual Review | 1.0000 | ✅ Yes | 0.0575 | `Strong Match` | **Manual Review Required** |
| `CLM-01178` | Consumer Electronics | Motherboard failure | Manual Review | 0.9924 | Manual Review | 1.0000 | ✅ Yes | 0.0076 | `Strong Match` | **Manual Review Required** |
| `CLM-00134` | Home Appliances | Electronic PCB failure | Valid Claim | 0.9987 | Valid Claim | 1.0000 | ✅ Yes | 0.0013 | `Strong Match` | **Likely Valid** |
| `CLM-00278` | Industrial & Automotive Tools | Trigger switch failure | Valid Claim | 0.9945 | Valid Claim | 1.0000 | ✅ Yes | 0.0055 | `Strong Match` | **Likely Valid** |
| `CLM-00403` | Industrial & Automotive Tools | Trigger switch failure | Valid Claim | 0.9998 | Valid Claim | 1.0000 | ✅ Yes | 0.0002 | `Strong Match` | **Likely Valid** |
| `CLM-00433` | Consumer Electronics | Speaker malfunction | Valid Claim | 1.0000 | Valid Claim | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Likely Valid** |
| `CLM-00428` | Consumer Electronics | Bluetooth/Wi-Fi failure | Valid Claim | 1.0000 | Valid Claim | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Likely Valid** |
| `CLM-00010` | Home Appliances | Motor burnout | Valid Claim | 0.9910 | Valid Claim | 1.0000 | ✅ Yes | 0.0090 | `Strong Match` | **Likely Valid** |
| `CLM-00429` | Home Appliances | Water pump leakage | Valid Claim | 0.9952 | Valid Claim | 1.0000 | ✅ Yes | 0.0048 | `Strong Match` | **Likely Valid** |
| `CLM-00486` | Consumer Electronics | Motherboard failure | Valid Claim | 1.0000 | Valid Claim | 1.0000 | ✅ Yes | 0.0000 | `Strong Match` | **Likely Valid** |
| `CLM-00253` | Home Appliances | Thermostat failure | Valid Claim | 0.9987 | Valid Claim | 1.0000 | ✅ Yes | 0.0013 | `Strong Match` | **Likely Valid** |
| `CLM-00435` | Industrial & Automotive Tools | Hydraulic pressure seal failure | Valid Claim | 0.9840 | Valid Claim | 1.0000 | ✅ Yes | 0.0160 | `Strong Match` | **Likely Valid** |
