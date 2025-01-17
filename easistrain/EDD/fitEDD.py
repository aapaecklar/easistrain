import os
from typing import Sequence, Optional, Tuple, Union

import numpy
import h5py

from easistrain.EDD.detector_fit import fit_all_peaks_and_save_results
from easistrain.EDD.io import (
    create_fit_info_group,
    peak_dataset_data,
    read_detector_pattern,
    read_positioner_data,
)
from easistrain.EDD.utils import run_from_cli


def fitEDD(
    fileRead: str,
    fileSave: str,
    sample: Optional[str],
    dataset: Union[str, int, None],
    scanNumber: Union[str, int],
    nameHorizontalDetector: str,
    nameVerticalDetector: str,
    positioners: Sequence[str],
    nbPeaksInBoxes: Sequence[int],
    rangeFitHD: Sequence[int],
    rangeFitVD: Sequence[int],
    detectorSliceIndex: Union[int, Tuple[()], None] = tuple(),
):
    print(f"Fitting scan n.{scanNumber}")
    # detectorSliceIndex can be None if present in the config file but not set
    if detectorSliceIndex is None:
        detectorSliceIndex = tuple()

    patternHorizontalDetector = read_detector_pattern(
        fileRead,
        sample,
        dataset,
        scanNumber,
        nameHorizontalDetector,
        detectorSliceIndex,
    )
    patternVerticalDetector = read_detector_pattern(
        fileRead, sample, dataset, scanNumber, nameVerticalDetector, detectorSliceIndex
    )

    patternHorizontalDetector = numpy.atleast_2d(patternHorizontalDetector)
    patternVerticalDetector = numpy.atleast_2d(patternVerticalDetector)
    nDetectorPoints = len(patternHorizontalDetector)

    if os.path.dirname(fileSave):
        os.makedirs(os.path.dirname(fileSave), exist_ok=True)
    with h5py.File(fileSave, "a") as h5Save:  ## Read the h5 file of raw data
        scanGroup = h5Save.create_group(
            f"{sample}_{dataset}_{scanNumber}.1"
        )  ## create the group of the scan wich will contatin all the results of a scan
        positionersGroup = scanGroup.create_group(
            "positioners"
        )  ## positioners subgroup in scan group
        positionAngles = numpy.zeros((nDetectorPoints, 6), "float64")

        for i, positioner in enumerate(positioners):
            pos_data = read_positioner_data(
                fileRead, sample, dataset, scanNumber, positioner, detectorSliceIndex
            )
            positionersGroup.create_dataset(
                positioner,
                dtype="float64",
                data=pos_data,
            )
            try:
                positionAngles[:, i] = pos_data
            except IndexError:
                print("Too many positioners given ! Only 6 are handled for now.")

        rawDataLevel1_1 = scanGroup.create_group(
            "rawData" + "_" + str(dataset) + "_" + str(scanNumber)
        )  ## rawData subgroup in scan group
        fitGroup = scanGroup.create_group("fit")  ## fit subgroup in scan group
        tthPositionsGroup = scanGroup.create_group(
            "tthPositionsGroup"
        )  ## two theta positions subgroup in scan group
        rawDataLevel1_1.create_dataset(
            "horizontalDetector", dtype="float64", data=patternHorizontalDetector
        )  ## save raw data of the horizontal detector
        rawDataLevel1_1.create_dataset(
            "verticalDetector", dtype="float64", data=patternVerticalDetector
        )  ## save raw data of the vertical detector

        for k in range(nDetectorPoints):
            pointInScan = fitGroup.create_group(
                f"{str(k).zfill(4)}"
            )  ## create a group of each pattern (point of the scan)

            (
                fitParamsHD,
                fitParamsVD,
                uncertaintyFitParamsHD,
                uncertaintyFitParamsVD,
            ) = fit_all_peaks_and_save_results(
                nbPeaksInBoxes,
                rangeFit={"horizontal": rangeFitHD, "vertical": rangeFitVD},
                patterns={
                    "horizontal": patternHorizontalDetector[k],
                    "vertical": patternVerticalDetector[k],
                },
                scanNumbers={
                    "horizontal": scanNumber,
                    "vertical": scanNumber,
                },
                saving_dest=pointInScan,
                group_format=lambda i: f"fitLine_{str(i).zfill(4)}",
            )

            for peakNumber in range(numpy.sum(nbPeaksInBoxes)):
                if f"peak_{str(peakNumber).zfill(4)}" not in tthPositionsGroup.keys():
                    peakDataset = tthPositionsGroup.create_dataset(
                        f"peak_{str(peakNumber).zfill(4)}",
                        dtype="float64",
                        data=numpy.zeros((2 * nDetectorPoints, 13), "float64"),
                    )  ## create a dataset for each peak in tthPositionGroup
                    uncertaintyPeakDataset = tthPositionsGroup.create_dataset(
                        f"uncertaintyPeak_{str(peakNumber).zfill(4)}",
                        dtype="float64",
                        data=numpy.zeros((2 * nDetectorPoints, 13), "float64"),
                    )  ## create a dataset for uncertainty for each peak in tthPositionGroup
                else:
                    peakDataset = tthPositionsGroup[f"peak_{str(peakNumber).zfill(4)}"]
                    assert isinstance(peakDataset, h5py.Dataset)
                    uncertaintyPeakDataset = tthPositionsGroup[
                        f"uncertaintyPeak_{str(peakNumber).zfill(4)}"
                    ]
                    assert isinstance(uncertaintyPeakDataset, h5py.Dataset)
                peakDataset[2 * k] = peak_dataset_data(
                    positionAngles, fitParamsHD[peakNumber], -90, k
                )
                peakDataset[2 * k + 1] = peak_dataset_data(
                    positionAngles, fitParamsVD[peakNumber], 0, k
                )
                uncertaintyPeakDataset[2 * k] = peak_dataset_data(
                    positionAngles, uncertaintyFitParamsHD[peakNumber], -90, k
                )
                uncertaintyPeakDataset[2 * k + 1] = peak_dataset_data(
                    positionAngles, uncertaintyFitParamsVD[peakNumber], 0, k
                )
            if "infoPeak" not in tthPositionsGroup.keys():
                tthPositionsGroup.create_dataset(
                    "infoPeak",
                    dtype=h5py.string_dtype(encoding="utf-8"),
                    data=f"{positioners}, delta, theta, position in channel, Intenstity, FWHM, shape factor, goodness factor",
                )  ## create info about dataset saved for each peak in tthPositionGroup

        create_fit_info_group(
            scanGroup,
            fileRead,
            fileSave,
            sample,
            dataset,
            scanNumber,
            nameHorizontalDetector,
            nameVerticalDetector,
            nbPeaksInBoxes,
            rangeFitHD,
            rangeFitVD,
            positioners,
        )


def fitEDD_with_scan_number_parse(**config):
    """Wrapper function to allow scanNumber to be a list or a slice."""
    n_scan_arg = config.pop("scanNumber")
    if isinstance(n_scan_arg, int):
        fitEDD(**config, scanNumber=n_scan_arg)
    elif isinstance(n_scan_arg, list):
        for i in n_scan_arg:
            fitEDD_with_scan_number_parse(**config, scanNumber=i)
    elif isinstance(n_scan_arg, str):
        if ":" in n_scan_arg:
            min_scan, max_scan = n_scan_arg.split(":")
            for i in range(int(min_scan), int(max_scan)):
                fitEDD(**config, scanNumber=i)
        else:
            fitEDD(**config, scanNumber=int(n_scan_arg))
    else:
        raise ValueError(f"Unrecognized value for scanNumber: {n_scan_arg}")


if __name__ == "__main__":
    run_from_cli(fitEDD_with_scan_number_parse)
