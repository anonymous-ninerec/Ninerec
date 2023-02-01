from torch.utils.data import Dataset

import torch
import numpy as np
import pandas as pd
from PIL import Image
import torchvision.transforms as transforms
import torchvision
import lmdb
import pickle
import random
import math
import os
from transformers import BertModel, BertTokenizer, BertConfig
tmp_l = ['douyin', 'kuai', 'qb', 'nc']
# Image_Mean = [0.4860599,  0.4426124,  0.43379018]
# Image_Std = [0.31636897, 0.3010678,  0.30478135]

Image_Mean = [0.5,  0.5,  0.5]
Image_Std = [0.5, 0.5,  0.5]
Resize = 224

class imgBatchDataset(Dataset):
    def __init__(self,config,dataload):
        self.item_num = dataload.item_num
        self.item_list = dataload.id2token['item_id']
        
        
        self.db_path = config['image_path']
       
        if 'BERT4Rec' in config['model']:
            self.length = self.item_num+1
        else :
            self.length = self.item_num

        self.load_content()
    
    def __len__(self):
        return self.length  #bert4rec这里加了1 ！！！ 

    def load_content(self):           
        self.env = lmdb.open(self.db_path, subdir=os.path.isdir(self.db_path),
                            readonly=True, lock=False,
                            readahead=False, meminit=False)
        self.feature_extractor = transforms.Compose([
            transforms.Resize((Resize,Resize)),
            transforms.ToTensor(),
            #transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))  
            transforms.Normalize(mean=Image_Mean, std=Image_Std)         

        ])
        
        self.reserve_embedding = torch.zeros(3,Resize,Resize)
        self.mask_embedding = torch.ones(3,Resize,Resize)

       
    def __getitem__(self, index):      
        item_i = index
        if index == 0 or index == self.item_num:
            if index == 0:
                item_i = self.reserve_embedding
            else:
                item_i = self.mask_embedding
        else :
            item_token_i = self.item_list[index]

            with self.env.begin() as txn:
                byteflow_i = txn.get(item_token_i.encode('ascii'))
                IMAGE_i = pickle.loads(byteflow_i)
                item_i = self.feature_extractor(Image.fromarray(IMAGE_i.get_image()).convert('RGB'))          
        return item_i

class BatchDataset(Dataset):
    def __init__(self,config,dataload):
        self.item_num = dataload.item_num
        self.item_list = dataload.id2token['item_id']
        
        
        self.db_path = config['image_path']
       
        if 'BERT4Rec' in config['model']:
            self.length = self.item_num+1
        else :
            self.length = self.item_num
        
        self.dataname = config['dataset']
        self.data_path = config['data_path']
        self.load_content()
    
    def __len__(self):
        return self.length 


    def load_content(self):
        if self.dataname not in tmp_l:
            text = pd.read_csv(f'{self.data_path}/text.csv', low_memory=False, encoding='utf-8', usecols=[0, 3], header=None,index_col=0)
            text.columns = ['title']
        else:
            text = pd.read_csv(f'{self.data_path}/text.csv', low_memory=False, encoding='utf-8', usecols=[0, 1], header=None,index_col=0)
            text.columns = ['title']
        
        bert_model_load = 'hfl/chinese-bert-wwm'
        item_content = text.to_dict()['title'] 
        tokenizer = BertTokenizer.from_pretrained(bert_model_load)
        item_dict = {}
        for k , v in item_content.items():
            item_dict[str(k)] = tokenizer(v, max_length=30,padding='max_length', truncation=True)
        self.item_content = item_dict

       
    def __getitem__(self, index):      
        item_i = index
        if index == 0 or index == self.item_num:
            if index == 0:
                item_i = [0]*60
            else:
                item_i = [0]*60
        else :
            item_token_i = self.item_list[index]

            item_i = self.item_content[item_token_i]['input_ids'] + self.item_content[item_token_i]['attention_mask']
        return torch.tensor(item_i, dtype=torch.int)