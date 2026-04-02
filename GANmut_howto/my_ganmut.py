import os
from pathlib import Path
import sys

import dlib
# import matplotlib.pyplot as plt
import torch
import cv2
from imutils.face_utils import rect_to_bb
import numpy as np

sys.path.append('../')
from models.model_linear_2d import Generator as Generator_l2
from models.model_gaussian_2d import Generator as Generator_g2


class GANmut:

    def __init__(self, G_path, model='linear', g_conv_dim=64, c_dim=7, g_repeat_num=6):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print("Device:", self.device)
        self.model = model

        if self.model == 'linear':
            self.G = Generator_l2(self.device, g_conv_dim, c_dim, g_repeat_num)

        elif self.model == 'gaussian':
            self.G = Generator_g2(self.device, g_conv_dim, c_dim, g_repeat_num)

        else:
            raise ValueError("choose either model='linear' or model='gaussian'")

        self.G.load_state_dict(torch.load(G_path, map_location=lambda storage, loc: storage))
        self.G.to(self.device)
        self.detector = dlib.get_frontal_face_detector()

    def blend_face(self, og_img, edited_crop, bbox):
        """
        Blend edited face into og image using Poisson blending.
        Args:
            og_img: NumPy array of og image (H, W, 3)
            edited_crop: NumPy array of GANmut output (h, w, 3)
            bbox: Tuple of (x_min, y_min, x_max, y_max) for the face in the og img.
        """
        x_min, y_min, x_max, y_max = bbox
        box_width = x_max - x_min
        box_height = y_max - y_min

        # resize GANmut output to match og bounding box size
        src = cv2.resize(edited_crop, (box_width, box_height))
        dst = og_img

        # create ellipse mask not rectangle
        # if mask touches edge of 'src' image, seamlessClone will
        # sample harsh edge and create weird artifacts
        mask = np.zeros(src.shape, src.dtype)
        center_of_src = (box_width // 2, box_height // 2)
        
        # make ellipse 80% of bounding box size to leave a safe border
        axes = (int(box_width * 0.4), int(box_height * 0.4))
        cv2.ellipse(mask, center_of_src, axes, 0, 0, 360, (255, 255, 255), -1)

        # calculate center target in destination image
        center_x = x_min + (box_width // 2)
        center_y = y_min + (box_height // 2)
        center_of_dst = (center_x, center_y)

        # execute the Seamless Clone
        # cv2.NORMAL_CLONE: preserves original texture of GANmut face but matches lighting.
        # cv2.MIXED_CLONE: mixes textures (often makes faces look transparent/ghostly)
        blended_image = cv2.seamlessClone(src, dst, mask, center_of_dst, cv2.NORMAL_CLONE)

        return blended_image

    def emotion_edit(self, img_path, x=None, y=None, theta=None, rho=None, save=False):

        if self.model == 'linear':
            assert (rho is not None) or (theta is not None), 'if model is linear you must provide rho and theta'
        else:
            assert (x is not None) and (y is not None), 'if model is gaussian you must provide x and y'

        img = cv2.imread(img_path, 1)  # BGR
        img_rgb = img[:, :, [2, 1, 0]]

        og_img_bgr = img.copy()

        # extract face
        dets = self.detector(img, 1)
        if not dets or len(dets) == 0:
            raise ValueError("No recognizable human face detected in the image.")
        det = dets[0]
        (xx, yy, w, h) = rect_to_bb(det)
        face = cv2.resize(img[yy:yy + h, xx:xx + w], (128, 128))

        # adapt image format for G
        face = face.transpose((2, 0, 1))  # [H,W,C] --> [C,H,W]
        face = (face / 255.0 - 0.5) / 0.5  # normalize to [-1, 1]
        face = torch.from_numpy(face).float().unsqueeze(0).to(self.device)

        # edit emotion

        with torch.no_grad():

            if self.model == 'linear':
                mode = 'manual_selection'
                expr = (torch.tensor([np.cos(theta), np.sin(theta)]) * rho).to(self.device).float()
                face_g = self.G(face, None, None, mode=mode, manual_expr=expr)[0][0, [2, 1, 0], :, :] / 2 + 0.5
            else:
                expr = torch.Tensor([x, y]).unsqueeze(0).to(self.device)
                face_g = self.G(face, expr)[0][0, [2, 1, 0], :, :] / 2 + 0.5

        face_g = face_g.transpose(0, 2).transpose(0, 1).detach().cpu().numpy()

        # insert edited face in original image

        # resize, scale to 0-255, and convert to uint8 for OpenCV
        edited_face_uint8 = (cv2.resize(face_g, (w, h)) * 255.0).astype(np.uint8)
        #img_rgb[yy:yy + h, xx:xx + w] = cv2.resize(face_g, (w, h)) * 255

        # create bounding box tuple (x_min, y_min, x_max, y_max)
        bbox = (xx, yy, xx + w, yy + h)

        # blend the face!
        # pass img_rgb as original image
        # overwrites old img_rgb with newly blended version
        img_rgb = self.blend_face(img_rgb, edited_face_uint8, bbox)

        if save:
            save_dir = "../edited_images"
            Path(save_dir).mkdir(parents=True, exist_ok=True)

            og_name = 'original_' + os.path.split(img_path)[-1]
            cv2.imwrite(os.path.join(save_dir, og_name), og_img_bgr)

            if self.model == 'linear':
                img_name = 'theta_{:0.2f}_rho_{:0.2f}'.format(theta, rho) + os.path.split(img_path)[-1]
            else:
                img_name = 'x_{:0.2f}_y_{:0.2f}'.format(x, y) + os.path.split(img_path)[-1]

            img_name = os.path.join(save_dir, img_name)
            
            cv2.imwrite(img_name, img_rgb[:,:, [2, 1, 0]])
            # plt.imsave(img_name, img_rgb)
            print(f'edited image saved in {img_name}')