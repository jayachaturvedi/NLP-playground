from code_utils.global_variables import *
from symptoms_classifier.NLP_embedding import clean_and_embed_text
import logging
import torch
import torch.nn.functional as F
import torch.nn as nn
import spacy
from sklearn.model_selection import train_test_split
import torch.optim as optim
import sklearn.metrics
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)

nlp = spacy.load(spacy_en_path, disable=['ner', 'parser'])
BATCH_SIZE = 100
DEVICE = torch.device("cpu")


def train_cnn(w2v, sentences, y, tokenization_type, keywords, ln=15, test_size=0.2, random_state=0, class_weight='balanced', dropout=0.5, n_epochs=5000):
    EMB_SIZE = w2v.wv.vector_size
    emb_weights, x_ind, c_ind = clean_and_embed_text(sentences=sentences, w2v=w2v, tokenization_type=tokenization_type, keywords=keywords, ln=ln)

    x_train, x_test, y_train, y_test, ind_train, ind_test = train_test_split(x_ind, y, c_ind, test_size=test_size, random_state=random_state)
    x_test = torch.tensor(x_test).to(DEVICE)
    y_test = torch.tensor(y_test).to(DEVICE)

    class CNN(nn.Module):
        def __init__(self, emb_weights, vocab_size, emb_size, kernel_sizes=[4, 3, 3]):
            super(CNN, self).__init__()
            self.embeddings = nn.Embedding(vocab_size, emb_size)
            self.embeddings.load_state_dict({'weight': torch.tensor(emb_weights, dtype=torch.float32)})
            self.embeddings.weight.requires_grad = False
            n_f = 128

            self.conv1 = nn.Conv2d(1, n_f, (kernel_sizes[0], emb_size))
            self.conv2 = nn.Conv2d(1, n_f, (kernel_sizes[1], emb_size))
            self.conv3 = nn.Conv2d(1, n_f, (kernel_sizes[2], emb_size))
            self.dropout = nn.Dropout(0.5)
            self.fc = nn.Linear(len(kernel_sizes) * n_f, 2)

        def conv_block(self, input, conv):
            out = conv(input)
            out = F.relu(out.squeeze(3))
            out = F.max_pool1d(out, out.size()[2]).squeeze(2)
            return out

        def forward(self, x):
            x = self.embeddings(x)
            x = x.unsqueeze(1)

            x1 = self.conv_block(x, self.conv1)
            x2 = self.conv_block(x, self.conv2)
            x3 = self.conv_block(x, self.conv3)

            x_all = torch.cat((x1, x2, x3), 1)
            x_all = self.dropout(x_all)
            logits = self.fc(x_all)
            return logits

    cnn = CNN(emb_weights, len(emb_weights), EMB_SIZE)
    optimizer = optim.Adam(cnn.parameters(), lr=0.0003)
    criterion = nn.CrossEntropyLoss(weight=torch.tensor([0.05, 0.95]))

    n_batches = len(x_train) // BATCH_SIZE
    for epoch in range(50):
        cnn.eval()
        outputs = torch.max(cnn(x_test), 1)[1]
        al = sklearn.metrics.classification_report(outputs.detach().numpy(), y_test.detach().numpy())
        f1 = sklearn.metrics.f1_score(outputs.detach().numpy(), y_test.detach().numpy())
        print(al)
        print(f1)

        for b_ind in range(n_batches):
            cnn.train()
            start = b_ind * BATCH_SIZE
            end = (b_ind + 1) * BATCH_SIZE
            x_batch = torch.tensor(x_train[start:end]).to(DEVICE)
            y_batch = torch.tensor(y_train[start:end]).to(DEVICE)

            optimizer.zero_grad()
            outputs = cnn(x_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()

    cnn.eval()
    logits = F.softmax(cnn(x_test), dim=1)
    outputs = torch.max(cnn(x_test), 1)[1]