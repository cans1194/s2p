#!/usr/bin/env python

import numpy as np
from python import common
from python import rpc_model
from python import pointing_accuracy
from python import rectification
from python import block_matching
from python import triangulation
from python import fusion
from python import geographiclib
from python import global_params
from shutil import copyfile


def process_pair(img_name, exp_name, x=None, y=None, w=None, h=None,
        reference_image_id=1, secondary_image_id=2, work_dir='/tmp',
        A_global=None):
    """
    Computes a height map from a pair of Pleiades images.

    Args:
        img_name: name of the dataset, located in the 'pleiades_data/images'
            directory
        exp_name: string used to identify the experiment
        x, y, w, h: four integers defining the rectangular ROI in the reference
            image. (x, y) is the top-left corner, and (w, h) are the dimensions
            of the rectangle.
        reference_image_id: id (1, 2 or 3 for the tristereo datasets, and 1 or
            2 for the bistereo datasets) of the image used as the reference
            image of the pair
        secondary_image_id: id of the image used as the secondary image of the
            pair
        work_dir (optional): directory in which the directory containing the
            results will be written
        A_global (optional): global pointing correction matrix, used for
            triangulation (but not for stereo-rectification)

    Returns:
        path to the height map, resampled on the grid of the reference image.
    """

    # input files
    im1 = 'pleiades_data/images/%s/im%02d.tif' % (img_name, reference_image_id)
    im2 = 'pleiades_data/images/%s/im%02d.tif' % (img_name, secondary_image_id)
    rpc1 = 'pleiades_data/rpc/%s/rpc%02d.xml' % (img_name, reference_image_id)
    rpc2 = 'pleiades_data/rpc/%s/rpc%02d.xml' % (img_name, secondary_image_id)
    prev1 = 'pleiades_data/images/%s/prev%02d.jpg' % (img_name, reference_image_id)

    # output files
    out_dir = '%s/%s' % (work_dir, exp_name)
    common.run('mkdir %s' % out_dir)
    rect1 = '%s/%d.tif' % (out_dir, reference_image_id)
    rect2 = '%s/%d.tif' % (out_dir, secondary_image_id)
    outrpc1 = '%s/rpc%d.xml' % (out_dir, reference_image_id)
    outrpc2 = '%s/rpc%d.xml' % (out_dir, secondary_image_id)
    disp    = '%s/disp.pgm'   % (out_dir)
    mask    = '%s/mask.png'   % (out_dir)
    height  = '%s/height.tif' % (out_dir)
    rpc_err = '%s/rpc_err.tif'% (out_dir)
    height_unrect  = '%s/height_unrect.tif' % (out_dir)
    mask_unrect    = '%s/mask_unrect.png'   % (out_dir)
    subsampling_file = '%s/subsampling.txt' % (out_dir)
    pointing = '%s/pointing_correction_%02d_%02d.txt' % (out_dir,
        reference_image_id, secondary_image_id)


    ## select ROI
    try:
        print "ROI x, y, w, h = %d, %d, %d, %d" % (x, y, w, h)
    except TypeError:
        x, y, w, h = common.get_roi_coordinates(rpc1, prev1)
        print "ROI x, y, w, h = %d, %d, %d, %d" % (x, y, w, h)

    ## correct pointing error - no subsampling!
    A = pointing_accuracy.compute_correction(img_name, x, y, w, h,
        reference_image_id, secondary_image_id)

    ## copy the rpcs to the output directory, save the subsampling factor and
    # the pointing correction matrix
    copyfile(rpc1, outrpc1)
    copyfile(rpc2, outrpc2)
    np.savetxt(pointing, A)
    np.savetxt(subsampling_file, np.array([global_params.subsampling_factor]))

    # ATTENTION if subsampling_factor is set the rectified images will be
    # smaller, and the homography matrices and disparity range will reflect
    # this fact

    ## rectification
    H1, H2, disp_min, disp_max = rectification.rectify_pair(im1, im2, rpc1,
        rpc2, x, y, w, h, rect1, rect2, A)

    ## block-matching
    block_matching.compute_disparity_map(rect1, rect2, disp, mask,
        global_params.matching_algorithm, disp_min, disp_max)

    ## triangulation
    if A_global is not None:
        triangulation.compute_height_map(rpc1, rpc2, H1, H2, disp, mask,
                height, rpc_err, A_global)
    else:
        triangulation.compute_height_map(rpc1, rpc2, H1, H2, disp, mask,
                height, rpc_err, A)

    try:
        zoom = global_params.subsampling_factor
    except NameError:
        zoom = 1
    tmp_crop = common.image_crop_TIFF(im1, x, y, w, h)
    ref_crop = common.image_safe_zoom_fft(tmp_crop, zoom)
    triangulation.transfer_map(height, ref_crop, H1, x, y, zoom, height_unrect)
    triangulation.transfer_map(mask, ref_crop, H1, x, y, zoom, mask_unrect)

#    ## cleanup
#    while common.garbage:
#        common.run('rm ' + common.garbage.pop())

    ## display results
    print "v %s %s %s %s" % (rect1, rect2, disp, mask)

    return height_unrect


def process_triplet(img_name, exp_name, x=None, y=None, w=None, h=None,
    reference_image_id=2, left_image_id=1, right_image_id=3):
    """
    Computes a height map from three Pleiades images.

    Args:
        img_name: name of the dataset, located in the 'pleiades_data/images'
            directory
        exp_name: string used to identify the experiment
        x, y, w, h: four integers defining the rectangular ROI in the reference
            image.  (x, y) is the top-left corner, and (w, h) are the dimensions of
            the rectangle.
        reference_image_id: id (1, 2 or 3) of the image used as the reference
            image of the triplet
        left_image_id: id of the image used as the secondary image of the first
            pair.
        right_image_id: id of the image used as the secondary image of the
            second pair.

    Returns:
        path to the height map, resampled on the grid of the reference image.
    """

    # select ROI
    try:
        print "ROI x, y, w, h = %d, %d, %d, %d" % (x, y, w, h)
    except TypeError:
        rpc = 'pleiades_data/rpc/%s/rpc%02d.xml' % (img_name, reference_image_id)
        prev = 'pleiades_data/images/%s/prev%02d.jpg' % (img_name, reference_image_id)
        x, y, w, h = common.get_roi_coordinates(rpc, prev)
        print "ROI x, y, w, h = %d, %d, %d, %d" % (x, y, w, h)

    exp_dir = '/tmp/%s' % exp_name
    common.run('mkdir %s' % exp_dir)

    # process the two pairs
    exp_name_left = '%s_left' % exp_name
    h_left = process_pair(img_name, exp_name_left, x, y, w, h,
        reference_image_id, left_image_id, exp_dir)

    exp_name_right = '%s_right' % exp_name
    h_right = process_pair(img_name, exp_name_right, x, y, w, h,
        reference_image_id, right_image_id, exp_dir)

    # merge the two height maps
    h = '%s/merged_height.tif' % (exp_dir)
    fusion.merge(h_left, h_right, 3, h)

    # cleanup
    while common.garbage:
        common.run('rm ' + common.garbage.pop())

    return h



if __name__ == '__main__':

    img_name = 'toulouse'
    exp_name = 'prison'
    x = 20380
    y = 18600
    w = 320
    h = 300

#    w = 700
#    h = 700
#
#    exp_name = 'aeroport'
#    x, y, w, h = 9197, 9630, 1892, 1847
#    img_name = 'calanques'
#    exp_name = 'collines'
#   x = 6600
#   y = 28800
#   w = 1000
#   h = 1000
#
#   img_name = 'cannes'
#   exp_name = 'theoule_sur_mer'
#   x = 5100
#   y = 32300
#   w = 1000
#   h = 1000
#
#    img_name = 'mera'
#    exp_name = 'crete'
#    x = 11127
#    y = 28545
#    w = 800
#    h = 800
#
#   img_name = 'new_york'
#   exp_name = 'manhattan'
#
#    img_name = 'ubaye'
#    exp_name = 'pic'
#    x = 11127
#    y = 13545
#    w = 800
#    h = 800
#
#   img_name = 'uy1'
#   exp_name = 'campo'
#   # FULL ROI
#   #x = 5500
#   #y = 13000
#   #w = 7000
#   #h = 10000
#   # portion inside ROI
#   x = 5500
#   y = 25000
#   w = 1500
#   h = 1500

# canvas_x = 5500
# canvas_y = 13000
# canvas_w = 3500
# canvas_h = 3500

#    img_name = 'montevideo'
#    exp_name = 'pza_independencia'
#    x, y, w, h = 13025, 26801, 2112, 1496
#    exp_name = 'fing_tvl1'
#    x, y, w, h = 19845, 29178, 1700, 1700

    # main call: STEREO PAIR
#    height_map = process_pair(img_name, exp_name, x, y, w, h, 2, 1)
#    generate_cloud(img_name, exp_name, x, y, w, h, height_map,
#        reference_image_id=2)

    # main call: TRISTEREO
    height_map = process_triplet(img_name, exp_name, x, y, w, h)
    generate_cloud(img_name, exp_name, x, y, w, h, height_map,
        reference_image_id=2)