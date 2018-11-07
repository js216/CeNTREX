%this program calculates the eigenenergies & eigenstates 
%of the TlF groundstate 
Jmax = 6;   %Max J value in Hamiltonian
I_Tl = 1/2;     %Setting up constants...this is I1 in Ramsey's notation
I_F = 1/2;    %Setting up constants...this is I2 in Ramsey's notation
%Loop over all J,m_J,m_I_F, m_I_Tl.  
%This defines ordering of states for a given index.
N_states = (2*I_Tl+1)*(2*I_F+1)*(Jmax+1)^2;  %Total number of states in Hilbert space considered
i_states = 0;  %index for state number in loop
QN = zeros(N_states,4);  %initialize array of quantum numbers for each basis state
%Loop to fill out array of quantum numbers for each basis state
for J = 0:Jmax;
    for m_J = -J:J;
        for m_I_Tl = -I_Tl:I_Tl;
            for m_I_F = -I_F:I_F;
                i_states = i_states+1;  %This sets the index for each basis state
                QN(i_states,:) = [J,m_J,m_I_Tl,m_I_F]; %quantum numbers of the basis state for this index
            end
        end
    end
end
%
%csvwrite('test1.dat',QN);  %write array of quantum numbers 
%
%generate field-free Hamiltonian
%H = Brot(J.J) + c1(I1.J) + c2(I2.J) + c4(I1.I2) +
%5c3[3(I1.J)(I2.J)+3(I2.J)(I1.J)-2(I1.I2)J.J]/[(2J+3)(2J+1)]
%set up constants for field-free Hamiltonian.  Everything in Hz.
% Data from D.A. Wilkening, N.F. Ramsey, and D.J. Larson, Phys Rev A 29,
% 425 (1984).
%
Brot = 6689920000;
c1 = 126030; %c1 =0; %
c2 = 17890; %c2 = 0; %
c3 = 700; %c3 = 0; %
c4 = -13300; %c4 = 0; %
%now create field-free Hamiltonian matrix
Ham_ff = zeros(N_states,N_states);
%
for i = 1:N_states;  %i = row number of H matrix, corresponds to BRA <J_i,m_J_i,m_Tl_i,m_F_i|
    J_i = QN(i,1); %rotational quantum number for state #i
    m_J_i = QN(i,2); %rotational projection for state #i
    m_Tl_i = QN(i,3); %Tl projection for state #i
    m_F_i = QN(i,4); %I projection for state #i
    for j = i:N_states;  % j = column number of H matrix, corresponds to KET |J_j,m_J_j,m_Tl_j,m_F_j>; indexing gives upper right part of matrix
        J_j = QN(j,1); %rotational quantum number for state #j
        m_J_j = QN(j,2); %rotational projection for state #j
        m_Tl_j = QN(j,3); %Tl projection for state #j
        m_F_j = QN(j,4); %I projection for state #j
        %
        %fill in rotational term
        %
        if j == i  %this means all quantum numbers m_F, m_Tl, m_J, and J are the same, so add rotational term
            Ham_ff(i,j) = Ham_ff(i,j)+ Brot*J_j*(J_j +1);
        end %end condition for diagonal matrix elements
        %for dot products, use the relation in terms of spin ladder ops
        %(NOT spherical tensor components...using ladder ops is just
        %a bit easier to code):  
        % A.B = AzBz + (A+B-)/2 + (A-B+)/2
        % J+|jm> = \sqrt{j(j+1)-m(m+1)}|j m+1>, 
        % J-|jm> = \sqrt{j(j+1)-m(m-1)}|j m-1>, Jz|jm> = m|jm>
        %
        % c1 term (I_Tl.J)
        if J_i == J_j && m_F_i == m_F_j %J and m_F have to match
            if m_J_i == m_J_j && m_Tl_i == m_Tl_j  %this is JzIz term.  Remember that j = ket, i = bra.
                Ham_ff(i,j) = Ham_ff(i,j)+ c1*m_J_j*m_Tl_j;
            elseif m_J_i == m_J_j +1 && m_Tl_i == m_Tl_j -1  %this is J+I- term. Remember that j = ket, i = bra.
                Ham_ff(i,j) = Ham_ff(i,j)+ c1*sqrt(J_j*(J_j +1)-m_J_j*(m_J_j +1))*sqrt(I_Tl*(I_Tl +1)- m_Tl_j*(m_Tl_j -1))/2;
            elseif m_J_i == m_J_j -1 && m_Tl_i == m_Tl_j +1  %this is J-I+ term. Remember that j = ket, i = bra.
                Ham_ff(i,j) = Ham_ff(i,j)+ c1*sqrt(J_j*(J_j +1)-m_J_j*(m_J_j -1))*sqrt(I_Tl*(I_Tl +1)- m_Tl_j*(m_Tl_j +1))/2;
            end
        end %end c1 term
        % c2 term (I_F.J)
        if J_i == J_j && m_Tl_i == m_Tl_j %J and m_Tl have to match
            if m_J_i == m_J_j && m_F_i == m_F_j  %this is JzIz term
                Ham_ff(i,j) = Ham_ff(i,j)+ c2*m_J_i*m_F_i;
            elseif m_J_i == m_J_j +1 && m_F_i == m_F_j -1  %this is J+I- term. Remember that j = ket, i = bra.
                Ham_ff(i,j) = Ham_ff(i,j)+ c2*sqrt(J_j*(J_j +1)-m_J_j*(m_J_j +1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j -1))/2;
            elseif m_J_i == m_J_j -1 && m_F_i == m_F_j +1  %this is J-I+ term. Remember that j = ket, i = bra.
                Ham_ff(i,j) = Ham_ff(i,j)+ c2*sqrt(J_j*(J_j +1)-m_J_j*(m_J_j -1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j +1))/2;
            end
        end %end c2 term
        %
        % first part of c3 term (2nd part appears later)
        % 15c3[(I1.J)(I2.J)+(I2.J)(I1.J)]/[(2J+3)(2J+1)]
        % write this out in term of ladder ops I1 I2 J J and
        % (here & is used instead of plus between terms, for clarity)
        % and rearrange in terms of change to m_J:
        % delta m_J = -2:  ++--/2
        % delta m_J = -1:  +z(-z & z-)/2 & + & z+(-z & z-)/2
        % delta m_J = 0: +-(+- & -+)/4 & -+(+- & -+)/4 & 2zzzz
        % delta m_J = +1: -z(+z & z+)/2 & + & z-(+z & z+)/2
        % delta m_J = +2: --++/2
        % OK, here goes with calculating c3 term:
        if J_i == J_j  %Js have to match
            cc3a = 15*c3/((2*J_j +3)*(2*J_j +1)); %this is a dummy variable, the effective coefficient for this value of J
            if m_J_i == m_J_j - 2 %delta m_J = -2
                if m_Tl_i == m_Tl_j + 1 && m_F_i == m_F_j + 1 %delta m_F = +1, delta m_Tl = +1
                factor = sqrt(J_j*(J_j +1)-m_J_j*(m_J_j -1))*sqrt(J_j*(J_j +1)-(m_J_j -1)*(m_J_j -2)); %two J lowering ops
                factor = factor * sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j +1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j +1)); %two I raising ops
                Ham_ff(i,j) = Ham_ff(i,j)+ cc3a*factor/2;
                end 
            elseif m_J_i == m_J_j - 1 %delta m_J = -1
                factor1 = sqrt(J_j*(J_j +1)-m_J_j*(m_J_j -1))*m_J_j; %J-Jz
                factor2 = (m_J_j-1)*sqrt(J_j*(J_j +1)-m_J_j*(m_J_j -1)); %JzJ-
                factor = factor1 + factor2;
                if m_Tl_i == m_Tl_j +1 && m_F_i == m_F_j %I1+ and I2z
                    Ham_ff(i,j) = Ham_ff(i,j)+ cc3a*factor*sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j +1))*m_F_j/2;
                elseif m_Tl_i == m_Tl_j && m_F_i == m_F_j +1 %I1z and I2+
                    Ham_ff(i,j) = Ham_ff(i,j)+ cc3a*factor*m_Tl_j*sqrt(I_F*(I_F +1)-m_F_j*(m_F_j +1))/2;
                end
            elseif m_J_i == m_J_j %delta m_J = 0
                if m_Tl_i == m_Tl_j && m_F_i == m_F_j %I1z and I2z
                    Ham_ff(i,j) = Ham_ff(i,j)+ cc3a*2*m_J_j*m_J_j*m_Tl_j*m_F_j;
                elseif m_Tl_i == m_Tl_j +1 && m_F_i == m_F_j -1 %I1+ and I2-
                    factor1 = sqrt(J_j*(J_j +1)-(m_J_j +1)*(m_J_j +1 -1))*sqrt(J_j*(J_j +1)-m_J_j*(m_J_j +1)); %J-J+
                    factor2 = sqrt(J_j*(J_j +1)-(m_J_j -1)*(m_J_j -1 +1))*sqrt(J_j*(J_j +1)-m_J_j*(m_J_j -1)); %J+J-
                    factor = factor1 + factor2;
                    Ham_ff(i,j) = Ham_ff(i,j)+ cc3a*factor*sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j +1))*sqrt(I_F*(I_F +1)-m_F_j*(m_F_j -1))/4;
                elseif m_Tl_i == m_Tl_j -1 && m_F_i == m_F_j +1 %I1- and I2+
                    factor1 = sqrt(J_j*(J_j +1)-(m_J_j +1)*(m_J_j +1 -1))*sqrt(J_j*(J_j +1)-m_J_j*(m_J_j +1)); %J-J+
                    factor2 = sqrt(J_j*(J_j +1)-(m_J_j -1)*(m_J_j -1 +1))*sqrt(J_j*(J_j +1)-m_J_j*(m_J_j -1)); %J+J-
                    factor = factor1 + factor2;
                    Ham_ff(i,j) = Ham_ff(i,j)+ cc3a*factor*sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j -1))*sqrt(I_F*(I_F +1)-m_F_j*(m_F_j +1))/4;
                end
            elseif m_J_i == m_J_j +1 %delta m_J = +1
                factor1 = sqrt(J_j*(J_j +1)-m_J_j*(m_J_j +1))*m_J_j; %J+Jz
                factor2 = (m_J_j-1)*sqrt(J_j*(J_j +1)-m_J_j*(m_J_j +1)); %JzJ+
                factor = factor1 + factor2;
                if m_Tl_i == m_Tl_j -1 && m_F_i == m_F_j %I1- and I2z
                    Ham_ff(i,j) = Ham_ff(i,j)+ cc3a*factor*sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j -1))*m_F_j/2;
                elseif m_Tl_i == m_Tl_j && m_F_i == m_F_j -1 %I1z and I2-
                    Ham_ff(i,j) = Ham_ff(i,j)+ cc3a*factor*m_Tl_j*sqrt(I_F*(I_F +1)-m_F_j*(m_F_j -1))/2;
                end
            elseif m_J_i == m_J_j + 2 %delta m_J = +2
                if m_Tl_i == m_Tl_j - 1 && m_F_i == m_F_j - 1 %delta m_F = -1, delta m_Tl = -1
                factor = sqrt(J_j*(J_j +1)-m_J_j*(m_J_j +1))*sqrt(J_j*(J_j +1)-(m_J_j +1)*(m_J_j +2)); %two J raising ops
                factor = factor * sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j -1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j -1)); %two I lowering ops
                Ham_ff(i,j) = Ham_ff(i,j)+ cc3a*factor/2;
                end
            end %end of possible delta m_J values for this first part of c3 term
        end  %end of condition that J's match for 1st part of c3 term
        %
        % c4 term c4(I_Tl.I_F) and 2nd part of c3 term:
        % -10c3(I1.I2)J(J+1)/[(2J+3)(2J+1)]
        if J_i == J_j && m_J_i == m_J_j %J and m_J have to match
            cc34 = c4 - 10*c3*J_j*(J_j +1)/((2*J_j + 3)*(2*J_j + 1));  %dummy variable, effective c4 term for this J
            if m_Tl_i == m_Tl_j && m_F_i == m_F_j  %this is I1zI2z term
                Ham_ff(i,j) = Ham_ff(i,j)+ cc34*m_Tl_j*m_F_j;
            elseif m_Tl_i == m_Tl_j +1 && m_F_i == m_F_j -1  %this is I1+I2- term
                Ham_ff(i,j) = Ham_ff(i,j)+ cc34*sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j +1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j -1))/2;
            elseif m_Tl_i == m_Tl_j -1 && m_F_i == m_F_j +1  %this is I1-I2+ term
                Ham_ff(i,j) = Ham_ff(i,j)+ cc34*sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j -1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j +1))/2;
            end 
        end %end c4 + 2nd part of c3 term
        %symmetrize Hamiltonian matrix
        Ham_ff(j,i) = Ham_ff(i,j);
        %
    end  %end loop over index j
end  %end loop over index i
%[V,D] = eig(Ham_ff);        %find eigenvalues D and eigenvectors V of Hamiltonian
%subtract away rotational energy for easier viewing of hyperfine
%substructure
%hfs_mat = zeros(N_states,N_states);
%for i=1:N_states
    %J_i = QN(i,1);
    %hfs_mat(i,i) = D(i,i) - J_i*(J_i +1)*Brot; %subtract rotational energy
%end
%hfs_kHz = diag(hfs_mat)/1000;  %change units to kHz for easier viewing
%stem(hfs_kHz)  %plot the hfs deviations from bare rotational structure(in kHz) in a stem plot
% OK, this completes the field-free Hamiltonian.  Now construct the
% Hamiltonian matrix for the Zeeman interaction.
% H_Z = -\mu_J(J.B)/J - \mu_1(I1.B)/I1 - \mu_2(I2.B)/I2
% Constants from Wilkening et al, in Hz/Gauss, for 205Tl
mu_J = 35;
mu_Tl = 1240.5;
mu_F = 2003.63;
%
% Construct Hamiltonian independent of B to start; mutliply by B at the end
% First, include B_z term only for simplicity.
%
Ham_Z_z = zeros(N_states,N_states);
%
for i = 1:N_states;
    J_i = QN(i,1); %rotational quantum number for state #i
    m_J_i = QN(i,2); %rotational projection for state #i
    m_Tl_i = QN(i,3); %Tl projection for state #i
    m_F_i = QN(i,4); %I projection for state #i
    for j = i:N_states;
        J_j = QN(j,1); %rotational quantum number for state #j
        m_J_j = QN(j,2); %rotational projection for state #j
        m_Tl_j = QN(j,3); %Tl projection for state #j
        m_F_j = QN(j,4); %I projection for state #j
        if J_i == J_j %condition for all Zeeman terms to be nonzero: diagonal in J, J nonzero
            %Bz term
            if m_J_i == m_J_j && m_Tl_i == m_Tl_j && m_F_i == m_F_j  %all quantum numbers m_F, m_Tl, m_J are the same, as needed for Bz term
                Ham_Z_z(i,j) = Ham_Z_z(i,j) - mu_Tl*m_Tl_j/I_Tl - mu_F*m_F_j/I_F;  %both nuclear spin Zeeman terms
                if J_i ~= 0 %rotational Zeeman, accounting for J=0 anomalous behavior
                    Ham_Z_z(i,j) = Ham_Z_z(i,j) - mu_J*m_J_j/J_j; %rotational Zeeman, accounting for J=0 anomalous behavior
                end %end rotational Zeeman term
            end %end Bz term
        end %end condition to be diagonal in J
        %symmetrize Hamiltonian matrix
        Ham_Z_z(j,i) = Ham_Z_z(i,j);
        %
    end  %end loop over index j
end  %end loop over index i
%Bz = 3.0; %Bz in Gauss
%Ham = Ham_ff + Bz*Ham_Z_z;
%[V,D] = eig(Ham);        %find eigenvalues D and eigenvectors V of Hamiltonian
%subtract away rotational energy 
%for easier viewing of hyperfine substructure
%hfs_mat = zeros(N_states,N_states);
%for i=1:N_states
%    J_i = QN(i,1);
%    hfs_mat(i,i) = D(i,i) - J_i*(J_i +1)*Brot; %subtract rotational energy
%end
%hfs_kHz = diag(hfs_mat)/1000;  %change units to kHz for easier viewing
%stem(hfs_kHz);  %plot the hfs deviations from bare rotational structure(in kHz) in a stem plot
%
% Now Stark Hamiltonian.
% As for Zeeman, first construct Hamiltonian idependent of E, then multiply
% by E at the end.
%
% molecular dipole moment D_TlF = 4.2282 Debye = 4.2282 * 0.393430307 ea_0
% D_TlF = 4.2282 * 0.393430307 *5.291772e-9 e.cm 
% so D_TlF * (Electric field in V/cm) is
% D_TlF*E[V/cm] = 4.2282 * 0.393430307 *5.291772e-9 * E[V/cm] eV 
% D_TlF*E[V/cm] = 4.2282 * 0.393430307 *5.291772e-9/4.135667e-15 *E[V/cm] Hz
% 
D_TlF = 4.2282 * 0.393430307 *5.291772e-9/4.135667e-15; %[Hz/(V/cm)]
% Include only E_z term.
%
Ham_St_z = zeros(N_states,N_states);
%
for i = 1:N_states;
    J_i = QN(i,1); %rotational quantum number for state #i
    m_J_i = QN(i,2); %rotational projection for state #i
    m_Tl_i = QN(i,3); %Tl projection for state #i
    m_F_i = QN(i,4); %I projection for state #i
    for j = i:N_states;
        J_j = QN(j,1); %rotational quantum number for state #j
        m_J_j = QN(j,2); %rotational projection for state #j
        m_Tl_j = QN(j,3); %Tl projection for state #j
        m_F_j = QN(j,4); %I projection for state #j
        %
        %  Stark Hamiltonian matrix elements must be diagonal in m_Tl and m_F,
        %  and have J' = J \pm 1.
        %  For E_z, also must be diagonal in m_J.
        %  For m_J = 0, <J \pm 1,0|H_St|j,0> given in J. Petricka thesis:
        %  = -dEz(J)/sqrt((2J-1)(2J+1)) [J' = J-1]
        %  = -dEz(J+1)/sqrt((2J+1)(2J+3)) [J' = J+1]
        %  For m_J \neq 0, get matrix element from Wigner-Eckhart theorem.
        %  This is worked out in detail in document
        %  "General form of rotational Stark matrix elements.docx"
        %  <J \pm 1,m|H_St|j,m>
        %  = -dEz sqrt( (J^2-m^2)/(4J^2-1) ) [J'=J-1]
        %  = -dEz sqrt( ((J+1)^2 - m^2)/(4(J+1)^2-1) ) [J'=J+1]
        %
        if m_F_i == m_F_j && m_Tl_i == m_Tl_j && m_J_i == m_J_j  %this ensures terms diagonal in m_F, m_Tl, and m_J
            if J_i == J_j -1
                Ham_St_z(i,j) = Ham_St_z(i,j) - D_TlF * sqrt((J_j^2-m_J_j^2)/(4*J_j^2 -1));
            elseif J_i == J_j +1
                Ham_St_z(i,j) = Ham_St_z(i,j) - D_TlF * sqrt(((J_j+1)^2-m_J_j^2)/(4*(J_j+1)^2 -1));
            end
        end
        %
        %symmetrize Hamiltonian matrix
        Ham_St_z(j,i) = Ham_St_z(i,j);
        %
    end  %end loop over index j
end  %end loop over index i
%
% OK!  Now we can construct the total Hamiltonian with Ez and Bz:
% Ham = Ham_ff + Bz*Ham_Z_z + Ez*Ham_St_z
%
% hfs_mat is a 1-D array to store energies for a given value of Ez, Bz
hfs_mat = zeros(N_states,1);
Bz = 18.4; %Bz in Gauss
%
% loop over different values of Ez
nEz_max = 100;
Energies = zeros(nEz_max+1,12);  %this is an array to store energies of J=1 states only, for all values of Ez in loop
Ez_array = zeros(nEz_max+1,1);  %this is an array of all the Ez values in the loop
for nEz = 0:nEz_max
    Ez = nEz*70.0/nEz_max;  %set the Ez value for this iteration of the loop
    Ez_array(nEz+1,1) = Ez;  %fill in the array of Ez values
    Ham = Ham_ff + Bz*Ham_Z_z + Ez*Ham_St_z;  %make the full Hamiltonian matrix for this value of Ez and Bz
    [V,D] = eig(Ham);        %find eigenvalues D and eigenvectors V of Hamiltonian
    %
    %subtract away rotational energy for easier viewing of substructure
    %
    for i=1:N_states
        J_i = QN(i,1);
        hfs_mat(i,1) = D(i,i) - J_i*(J_i +1)*Brot; %subtract rotational energy
    end
    hfs_kHz = hfs_mat/1000; %change units to kHz for easier viewing
    Energies(nEz+1,:) = hfs_kHz(5:16);  %fill in array of energies of J=1 states only, with one row for each value of Ez in loop
end
%
plot(Ez_array,Energies);  %plot the energies of the J=1 states vs. Ez
axis([0 80 -300 300]);  %set the axis limits to match the plot in Ramsey's paper
leg = zeros(12,1);
for i = 1:12
    leg(i,:) = i;
end
leg = num2str(leg);
legend(leg)