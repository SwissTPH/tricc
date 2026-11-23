// Test fixture: SwissTPH/global-almanach L4/drugs.js at 51f2505 (2025-10-29), unchanged below.
// The decision table tests turn it into tables and compare their doses with getDose.
// This is the drugs js file
// - Used in the Global almanac
// - Almanach-somalia
// See below comments to see how the drug doses are calculated
"use strict";

const dosesWeightClasses = [
  {
    acyclovir: {
      1: "",
      3: 1,
      6: 1,
      10: 1,
      12: 2,
      15: 2,
      20: 2,
    },
  },
  {
    ampicillin_yi: {
      1: "-",
      1.5: 0.6,
      2.5: 1,
      4: 1.3,
    },
  },
  {
    ampicillin: {
      1: "-",
      4: "1ml",
      6: "2ml",
      8: "2.5ml",
      10: "3ml",
      15: "5ml (2.5ml in each thigh)",
      20: "6ml (3 ml in each thigh)",
    },
  },
  {
    cloxacillin_oral: {
      3: "1/4",
      6: "1/2",
      10: "1",
      15: "1 1/2",
      20: "2 1/2",
    },
  },
  {
    griseofulvin_125: {
      3: "--",
      10: 1,
      14: 2,
    },
  },
  {
    griseofulvin_500: {
      3: "--",
      10: "1/4",
      14: "1/2",
    },
  },
  {
    artesunate_im: {
      3: 0.6,
      4: 0.8,
      6: 1.2,
      8: 1.5,
      10: 2,
      12: 2.5,
      18: 3,
    },
  },
  // Co-amoxiclav 4:1, both high and low dose in syrup form according to weight
  {
    amoxi_clavula_l_h_d_4_1: {
      3: "--",
      4: 4,
      6: 5,
      8: 7,
      10: 10,
      15: 15,
      20: 20,
    },
  },
  //CoAmoxiclav  Low dose 7:1 in syrup form
  {
    amoxi_clavula_l_d_7_1: {
      3: "--",
      4: 1.2,
      6: 2,
      8: 2.5,
      10: 3,
      12: 3.5,
      15: 4.5,
      20: 6,
    },
  },
  // Co-Amoxiclav 7:1 high dose in syrup form
  {
    amoxi_clavula_h_d_7_1: {
      3: "--",
      4: 1.5,
      6: 3.5,
      8: 5,
      10: 6,
      12: 7,
      15: 9,
      20: 12,
    },
  },
  //FIXME: cannot find this in the diagram for YI
  {
    amoxi_clavula_h_d_7_1_yi: {
      1: "-",
      1.5: "0.7",
      2.5: "1.1",
      4: "1.5",
    },
  },
  // Co-Amoxiclav 4:1 for both high and low dose in tablet form according to weight
  {
    amoxi_clavula_tab: {
      1: "-",
      4: "-",
      6: "-",
      8: "-",
      10: "1/2",
      15: "3/4",
      20: "1",
      30: "1",
    },
  },
  {
    amoxicillin_yi: {
      1: "-",
      1.5: 5,
      2.5: 5,
      4: 10,
      6: 10,
    },
  },
  {
    amoxicillin: {
      1.5: 5,
      3: 5,
      4: 7,
      4.5: 7,
      5: 7,
      6: 10,
      8: 15,
      10: 20,
      12: 20,
      15: 25,
      18: 25,
      20: 30,
    },
  },
  {
    amoxicillin_tab_yi: {
      1: "-",
      1.5: "1/2",
      2.5: "1/2",
      4: "1",
      6: "1",
    },
  },
  {
    amoxicillin_tab: {
      5: "-",
      6: "1",
      8: "1 1/2",
      10: "2",
      12: "2",
      15: "3",
      18: "3",
      20: "4",
    },
  },
  {
    arthemeter_lumefantrine_som: {
      3: 1,
      15: 2,
    },
  },
  {
    cefixim: {
      3: "-",
      4: 1.8,
      6: 2.8,
      8: 3.5,
      10: 5,
      12: 6,
      15: 7,
      20: 9,
    },
  },
  {
    ceftriaxone: {
      3: "1.3ml",
      4.5: "1.8ml",
      6: "2.4ml",
      8: "3ml",
      10: "4ml (2ml in each thigh)",
      12: "5ml (2.5ml in each thigh)",
      15: "6ml (3ml in each thigh)",
      20: "8ml (4ml in each thigh)",
    },
  },
  {
    ceftriaxone_yi: {
      1: "0.5ml",
      1.5: "0.7ml",
      2: "0.9ml",
      2.5: "1.1ml",
      3: "1.3ml",
      4.5: "1.8ml",
    },
  },
  {
    ciprofloxacine: {
      3: "-",
      4: "-",
      4.5: "-",
      5: "-",
      6: "1/4",
      10: "1/2",
      15: "1/2",
      20: "1",
    },
  },
  {
    diazepam: {
      3: 0.4,
      6: 0.75,
      10: 1.2,
      15: 1.7,
      20: 2.5,
    },
  },
  {
    erythromycin_c_tab: {
      3: "-",
      4: "-",
      4.5: "-",
      5: "-",
      6: "-",
      8: "-",
      10: "1",
      12: "1",
      15: "1",
      20: "1 1/2",
    },
  },
  {
    gentamicin: {
      3: "0.5ml",
      4: "0.7ml",
      5: "0.9ml",
      6: "1.1ml",
      8: "1.5ml",
      10: "1.9ml",
      12: "2.3ml",
      15: "2.8ml",
      18: "3.4 (1.7ml in each thigh)",
      20: "3.8 (1.9ml in each thigh)",
    },
  },
  {
    gentamicin_yi: {
      1.5: "0.2",
      2.5: "0.4",
      4: "0.6",
    },
  },
  {
    iron: {
      3: 2,
      6: 3,
      10: 5,
      15: 6,
      20: 10,
    },
  },
  {
    iron_tab: {
      8: "-",
      10: "1/2",
      15: "1",
      20: "1 1/2",
    },
  },
  {
    paracetamol_syrup_oral: {
      3: 1.5,
      4: 2.5,
      6: 4,
      10: 6,
      15: 8,
      20: 12,
    },
  },
  {
    paracetamol_tab_100: {
      1: "--",
      4: "1/2",
      6: 1,
      10: "1 1/2",
      15: 2,
      20: 3,
    },
  },
  {
    paracetamol_tab_500: {
      1: "--",
      6: "1/4",
      10: "1/4",
      15: "1/2",
      20: "1/2",
    },
  },
];

// Drug doses in age classes
const dosesAgeClasses = [
  {
    acyclovir: {
      2: 1,
      4: 1,
      12: 1,
      24: 2,
      36: 2,
      60: 2,
    },
  },
  {
    ampicillin: {
      2: "1ml",
      4: "2ml",
      9: "2.5ml",
      12: "3ml",
      36: "5ml (2.5ml in each thigh)",
    },
  },
  {
    cloxacillin_oral: {
      2: "1/4",
      4: "1/2",
      12: "1",
      36: "1 1/2",
    },
  },
  {
    diazepam: {
      2: 0.4,
      5: 0.75,
      12: 1.2,
      36: 1.7,
    },
  },
  {
    artesunate_im: {
      2: 0.6,
      3: 0.8,
      5: 1.2,
      10: 1.5,
      12: 2,
      24: 2.5,
      36: 2.5,
      48: 3,
    },
  },
  {
    albendazole_tab_prev: {
      2: "-",
      3: "-",
      4: "-",
      5: "-",
      6: "-",
      10: "-",
      12: "1/2",
      24: "1",
      60: 1,
    },
  },
  // Coamoxiclav for 4:1 dilution in both high and low doses in syrup form according to age
  {
    amoxi_clavula_l_h_d_4_1: {
      2: 4,
      4: 5,
      10: 7,
      12: 10,
      36: 15,
      60: 15,
    },
  },
  // Coamoxiclav for 4:1 dilution in both high and low doses in tablet form according to age
  {
    amoxi_clavula_tab: {
      2: "-",
      4: "-",
      10: "-",
      12: "1/2",
      36: "3/4",
      60: "3/4",
    },
  },
  {
    amoxi_clavula_l_d_7_1: {
      2: 1.2,
      4: 2,
      10: 2.5,
      12: 3,
      24: 3.5,
      36: 4.5,
      60: 4.5,
    },
  },
  {
    amoxi_clavula_h_d_7_1: {
      2: 1.5,
      4: 3.5,
      10: 5,
      12: 6,
      24: 7,
      36: 9,
      60: 9,
    },
  },
  {
    amoxicillin: {
      2: 5,
      3: 7,
      4: 10,
      10: 15,
      12: 20,
      36: 25,
      48: 25,
    },
  },
  {
    amoxicillin_tab: {
      2: "-",
      3: "-",
      4: 1,
      10: "1 1/2",
      12: 2,
      36: 3,
      48: 3,
    },
  },
  {
    arthemeter_lumefantrine_som: {
      2: 1,
      36: 2,
      48: 2,
    },
  },
  {
    cefixim: {
      2: 1.8,
      4: 2.8,
      10: 3.5,
      12: 5,
      24: 6,
      36: 7,
      48: 7,
    },
  },
  {
    ceftriaxone: {
      2: "1.3ml",
      3: "1.8ml",
      4: "2.4ml",
      10: "3ml",
      12: "4ml (2ml in each thigh)",
      24: "5ml (2.5ml in each thigh)",
      36: "6ml (3ml in each thigh)",
      48: "6ml (3ml in each thigh)",
    },
  },
  {
    gentamicin: {
      2: "0.5ml",
      3: "0.7ml",
      4: "0.9ml",
      6: "1.1ml",
      10: "1.5ml",
      12: "1.9ml",
      24: "2.3ml",
      36: "2.8ml",
      48: "3.4ml (1.7ml in each thigh)",
    },
  },
  {
    zinc: {
      2: "1/4",
    },
  },
  {
    vit_a: {
      2: 2,
      6: 4,
      12: 8,
    },
  },
  {
    paracetamol_syrup_oral: {
      1: "--",
      2: 2.5,
      4: 4,
      12: 6,
      36: 8,
    },
  },
  {
    paracetamol_tab_100: {
      0: "--",
      2: "1/2",
      4: "1",
      12: "1 1/2",
      36: "2",
    },
  },
  {
    paracetamol_tab_500: {
      0: "--",
      4: "1/4",
      36: "1/2",
    },
  },
  {
    ciprofloxacine: {
      3: "-",
      4: "1/4",
      12: "1/2",
    },
  },
  {
    erythromycin_c_tab: {
      2: "-",
      24: 1,
    },
  },
  {
    iron: {
      2: 2,
      4: 3,
      12: 5,
      36: 6,
    },
  },
  {
    iron_tab: {
      12: "1/2",
      36: "1",
    },
  },
  {
    griseofulvin_125: {
      10: "-",
      12: 1,
      36: 2,
    },
  },
  {
    griseofulvin_500: {
      10: "-",
      12: "1/4",
      36: "1/2",
    },
  },
];

const drugsWeight = [
  "acyclovir",
  "ampicillin_yi",
  "ampicillin",
  "cloxacillin_oral",
  "griseofulvin_125",
  "griseofulvin_500",
  "artesunate_im",
  "amoxi_clavula_l_h_d_4_1",
  "amoxi_clavula_l_d_7_1",
  "amoxi_clavula_h_d_7_1",
  "amoxi_clavula_h_d_7_1_yi",
  "amoxi_clavula_tab",
  "amoxicillin_yi",
  "amoxicillin",
  "amoxicillin_tab_yi",
  "amoxicillin_tab",
  "arthemeter_lumefantrine_som",
  "cefixim",
  "ceftriaxone",
  "ceftriaxone_yi",
  "ciprofloxacine",
  "diazepam",
  "erythromycin_c_tab",
  "gentamicin",
  "gentamicin_yi",
  "iron",
  "iron_tab",
  "paracetamol_syrup_oral",
  "paracetamol_tab_100",
  "paracetamol_tab_500",
];

const drugesAge = [
  "acyclovir",
  "ampicillin",
  "cloxacillin_oral",
  "diazepam",
  "artesunate_im",
  "albendazole_tab_prev",
  "amoxi_clavula_l_h_d_4_1",
  "amoxi_clavula_tab",
  "amoxi_clavula_l_d_7_1",
  "amoxi_clavula_h_d_7_1",
  "amoxicillin",
  "amoxicillin_tab",
  "arthemeter_lumefantrine_som",
  "cefixim",
  "ceftriaxone",
  "gentamicin",
  "zinc",
  "vit_a",
  "paracetamol_syrup_oral",
  "paracetamol_tab_100",
  "paracetamol_tab_500",
  "ciprofloxacine",
  "erythromycin_c_tab",
  "iron",
  "iron_tab",
  "griseofulvin_125",
  "griseofulvin_500",
];

const getSlice = (doseSlice, intVal) => {
  try {
    let prev = null;
    // Sort entries by numeric key value
    const sortedEntries = Object.entries(doseSlice).sort(
      ([a], [b]) => parseFloat(a) - parseFloat(b)
    );

    for (const [key, value] of sortedEntries) {
      if (intVal === parseFloat(key)) {
        return value;
      }
      if (intVal < parseFloat(key)) {
        return prev;
      }
      prev = value;
    }
    return prev;
  } catch (e) {
    console.log(`no dose found for: ${doseSlice}`);
    return null;
  }
};

/*
The drug doses are calculated following steps
The drugs are mapped in two arrays, which include drug according to the weight and the drug according to the age
The function getDose takes 3 parameters, the drug, the weight and the age,
The drug is fetched from both the drug for weight and the drug for age table
The weight is given priority over the age, and if weight is provided the age is ignored
Then the getSlice function first goes through the available values weight or age

The dose less than a given value is fetched,
for example if the weight is 15kg, and there is weight of 15 the dose below 15kg is selected
This follows Anja;s drug Matrix, where drug is selected les than a given weight or age, not less or equal to
*/

const getDose = (drug, age, weight) => {
  try {
    const drugWeightIndex = drugsWeight.indexOf(drug);
    const drugAgeIndex = drugesAge.indexOf(drug);
    if (drugWeightIndex == -1 && drugAgeIndex == -1) return null;
    const parseWeight = parseFloat(weight);

    if (isNaN(parseWeight) || parseWeight === 0 || !parseWeight) {
      if (drugAgeIndex == -1) return null;
      let doseSlice = dosesAgeClasses[drugAgeIndex][drug];
      const dose = getSlice(doseSlice, parseInt(age));
      return dose;
    }

    if (drugWeightIndex == -1) {
      let doseSlice = dosesAgeClasses[drugAgeIndex][drug];
      const doseForAge = getSlice(doseSlice, parseInt(age));
      console.log(`dose for ${drug} age: ${doseForAge}`);
      return doseForAge;
    } else {
      let doseSlice = dosesWeightClasses[drugWeightIndex][drug];
      if (drug === "ampicillin_yi") {
        console.log(doseSlice);
      }
      let dose = getSlice(doseSlice, parseWeight);
      if (dose !== null) return dose;
      doseSlice = dosesAgeClasses[drugAgeIndex][drug];
      const doseForAge = getSlice(doseSlice, parseInt(age));
      console.log(`dose for ${drug} weight ${weight}: ${dose}`);
      return doseForAge;
    }
  } catch (e) {
    console.log(e);
    console.log(`weight index: ${drugsWeight.indexOf(drug)}, ${drug}`);
    console.log(`no dose found for drug: ${drug}`);
    return null;
  }
};

const getValue = function (obj) {
  let val;
  if (obj.t === "arr") {
    val = obj.v && obj.v.length && obj.v[0];
  } else {
    val = obj.v;
  }
  return val;
};

const getDecimalValue = function (obj) {
  let val = getValue(obj);
  if (!val) {
    return null;
  }
  const parsed = parseFloat(val.textContent);
  return isNaN(parsed) ? 0 : parsed;
};

module.exports = function (drug, age, weight) {
  let decimalAge = getDecimalValue(age);
  let decimalWeight = getDecimalValue(weight);
  if (drug.v == void 0 || drug.v == "" || decimalAge == 0) {
    return { t: "str", v: "" };
  }
  let dose = getDose(drug.v, decimalAge, decimalWeight);
  if (dose == null) {
    return { t: "str", v: "" };
  }
  return { t: "str", v: dose.toString() };
};